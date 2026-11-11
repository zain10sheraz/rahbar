"""Stage 1: Extract. PDF (or HTML, or Markdown) to text, page by page."""

from __future__ import annotations

from .models import Document


import html
import re
from pathlib import Path

import pdfplumber
import pypdf
import pytesseract
from pdf2image import convert_from_path

from .models import Page


def _extract_pdf(file_path: Path) -> list[Page]:
    pages: list[Page] = []
    # Attempt extraction with pdfplumber first
    try:
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages, start=1):
                text = page.extract_text() or ""
                # Also extract tables formatted as text lines
                tables = page.extract_tables()
                if tables:
                    table_texts = []
                    for t in tables:
                        for row in t:
                            row_clean = [str(c or "").strip() for c in row if c]
                            if row_clean:
                                table_texts.append(" | ".join(row_clean))
                    if table_texts:
                        text = text + "\n" + "\n".join(table_texts)

                # If text is too sparse or empty, OCR the page
                if len(text.strip()) < 30:
                    try:
                        images = convert_from_path(
                            file_path, first_page=i, last_page=i, dpi=200
                        )
                        if images:
                            ocr_text = pytesseract.image_to_string(images[0])
                            if len(ocr_text.strip()) > len(text.strip()):
                                text = ocr_text
                                pages.append(Page(source=file_path.name, page=i, text=text, ocr=True))
                                continue
                    except Exception:
                        pass
                pages.append(Page(source=file_path.name, page=i, text=text, ocr=False))
    except Exception:
        # Fallback to pypdf
        reader = pypdf.PdfReader(str(file_path))
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append(Page(source=file_path.name, page=i, text=text, ocr=False))
    return pages


def _extract_html(file_path: Path) -> list[Page]:
    raw = file_path.read_text(encoding="utf-8", errors="ignore")
    # Simple regex-based HTML tag stripping and formatting
    # Remove script and style tags
    clean_html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
    # Convert breaks and paragraphs to newlines
    clean_html = re.sub(r"<(br|p|div|tr)[^>]*>", "\n", clean_html, flags=re.IGNORECASE)
    # Strip other tags
    clean_text = re.sub(r"<[^>]+>", " ", clean_html)
    clean_text = html.unescape(clean_text)
    # Collapse multiple blank lines
    lines = [line.strip() for line in clean_text.splitlines() if line.strip()]
    return [Page(source=file_path.name, page=1, text="\n".join(lines), ocr=False)]


def _extract_markdown_or_text(file_path: Path) -> list[Page]:
    text = file_path.read_text(encoding="utf-8", errors="ignore")
    return [Page(source=file_path.name, page=1, text=text, ocr=False)]


def extract(path: str, doc_version: str, superseded: bool) -> Document:
    """Return the document's text page by page.

    Detect pages with no text layer and OCR them; mark those pages ocr=True.
    """
    file_path = Path(path)
    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        pages = _extract_pdf(file_path)
    elif suffix in (".html", ".htm"):
        pages = _extract_html(file_path)
    else:
        pages = _extract_markdown_or_text(file_path)

    return Document(
        source=file_path.name,
        doc_version=doc_version,
        superseded=superseded,
        pages=pages,
    )
