"""Stage 3: Chunk. Structure-aware, with overlap."""

from __future__ import annotations

from .models import Chunk, Document


import hashlib
import re



_HEADING_REGEX = re.compile(
    r"^(?:#{1,6}\s+|(?:\d+\.)+\d*\s+|[A-Z0-9\.\s\-]{3,40}:)(.+)$"
)


def _approx_tokens(text: str) -> list[str]:
    """Simple whitespace token split (approximate word tokens)."""
    return text.split()


def chunk(doc: Document, size: int, overlap: int) -> list[Chunk]:
    """Split on sections, then paragraphs, then sentences, keeping each chunk under
    `size` tokens, with `overlap` tokens shared between neighbours. Every chunk keeps
    the section heading it sits under, its page, doc_version and superseded."""
    chunks: list[Chunk] = []
    chunk_index = 0
    current_section = "General"

    for page in doc.pages:
        paragraphs = page.text.split("\n\n")
        page_chunks_buffer: list[str] = []
        buffer_tokens = 0

        for para in paragraphs:
            para = para.strip()
            if not para:
                continue

            # Check if paragraph or first line is a section heading
            first_line = para.split("\n", 1)[0].strip()
            match = _HEADING_REGEX.match(first_line)
            if match or (len(first_line) < 60 and first_line.isupper() and len(first_line) > 3):
                # Flush existing buffer before changing section if non-empty
                if page_chunks_buffer:
                    chunk_text = " ".join(page_chunks_buffer)
                    chunk_id = hashlib.sha256(
                        f"{doc.source}-{page.page}-{chunk_index}-{chunk_text[:30]}".encode()
                    ).hexdigest()[:16]
                    chunks.append(
                        Chunk(
                            id=chunk_id,
                            text=chunk_text,
                            source=doc.source,
                            section=current_section,
                            page=page.page,
                            doc_version=doc.doc_version,
                            superseded=doc.superseded,
                        )
                    )
                    chunk_index += 1
                    # Keep overlap tokens for context
                    tokens = _approx_tokens(chunk_text)
                    page_chunks_buffer = [" ".join(tokens[-overlap:])] if overlap and len(tokens) > overlap else []
                    buffer_tokens = len(_approx_tokens(" ".join(page_chunks_buffer)))

                current_section = match.group(1).strip() if match else first_line

            words = _approx_tokens(para)
            if not words:
                continue

            # If single paragraph exceeds size, split paragraph into sub-slices
            if len(words) > size:
                start = 0
                step = max(1, size - overlap)
                while start < len(words):
                    slice_words = words[start : start + size]
                    chunk_text = " ".join(slice_words)
                    chunk_id = hashlib.sha256(
                        f"{doc.source}-{page.page}-{chunk_index}-{chunk_text[:30]}".encode()
                    ).hexdigest()[:16]
                    chunks.append(
                        Chunk(
                            id=chunk_id,
                            text=chunk_text,
                            source=doc.source,
                            section=current_section,
                            page=page.page,
                            doc_version=doc.doc_version,
                            superseded=doc.superseded,
                        )
                    )
                    chunk_index += 1
                    start += step
                continue

            # Otherwise accumulate paragraphs
            if buffer_tokens + len(words) > size:
                if page_chunks_buffer:
                    chunk_text = " ".join(page_chunks_buffer)
                    chunk_id = hashlib.sha256(
                        f"{doc.source}-{page.page}-{chunk_index}-{chunk_text[:30]}".encode()
                    ).hexdigest()[:16]
                    chunks.append(
                        Chunk(
                            id=chunk_id,
                            text=chunk_text,
                            source=doc.source,
                            section=current_section,
                            page=page.page,
                            doc_version=doc.doc_version,
                            superseded=doc.superseded,
                        )
                    )
                    chunk_index += 1
                    tokens = _approx_tokens(chunk_text)
                    page_chunks_buffer = [" ".join(tokens[-overlap:])] if overlap and len(tokens) > overlap else []
                    buffer_tokens = len(_approx_tokens(" ".join(page_chunks_buffer)))

            page_chunks_buffer.append(para)
            buffer_tokens += len(words)

        # Flush remaining buffer for this page
        if page_chunks_buffer:
            chunk_text = " ".join(page_chunks_buffer)
            chunk_id = hashlib.sha256(
                f"{doc.source}-{page.page}-{chunk_index}-{chunk_text[:30]}".encode()
            ).hexdigest()[:16]
            chunks.append(
                Chunk(
                    id=chunk_id,
                    text=chunk_text,
                    source=doc.source,
                    section=current_section,
                    page=page.page,
                    doc_version=doc.doc_version,
                    superseded=doc.superseded,
                )
            )
            chunk_index += 1

    return chunks
