"""Stage 2: Clean. Remove artefacts without destroying structure."""

from __future__ import annotations

from .models import Document


import re
from .models import Document, Page


def clean(doc: Document) -> Document:
    """Strip headers and footers that repeat on every page; keep headings and
    section boundaries, because chunking and citations depend on them."""
    cleaned_pages: list[Page] = []

    # Patterns for page numbers, running headers, and footers
    header_footer_patterns = [
        re.compile(r"^\s*page\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE),
        re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),
        re.compile(r"^\s*fast-nuces\s+academic\s+rules.*$", re.IGNORECASE),
        re.compile(r"^\s*national\s+university\s+of\s+computer.*$", re.IGNORECASE),
        re.compile(r"^\s*student\s+handbook.*$", re.IGNORECASE),
    ]

    for p in doc.pages:
        lines = p.text.splitlines()
        filtered_lines: list[str] = []
        for line in lines:
            line_str = line.strip()
            if not line_str:
                filtered_lines.append("")
                continue
            # Check against repetitive header/footer regexes
            if any(pat.match(line_str) for pat in header_footer_patterns):
                continue
            # Remove isolated page number lines at boundaries
            if line_str.isdigit() and len(line_str) <= 3:
                continue
            filtered_lines.append(line)

        cleaned_text = "\n".join(filtered_lines)
        # Normalize multiple successive blank lines to at most two
        cleaned_text = re.sub(r"\n{3,}", "\n\n", cleaned_text).strip()
        cleaned_pages.append(
            Page(source=p.source, page=p.page, text=cleaned_text, ocr=p.ocr)
        )

    return Document(
        source=doc.source,
        doc_version=doc.doc_version,
        superseded=doc.superseded,
        pages=cleaned_pages,
    )
