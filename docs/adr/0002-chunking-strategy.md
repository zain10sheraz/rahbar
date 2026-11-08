# ADR 0002: Structure-Aware Document Chunking Strategy

## Status
Accepted · 2026-11-08

## Context
Academic and regulatory documents (such as university handbooks, policy rules, and fee schedules) are organized hierarchically into clauses, sub-clauses, and tables. 
Fixed-character or purely fixed-token windowing splits text arbitrarily at token boundaries, often separating clause numbers (e.g. `1.21`) from their mandatory conditions or dividing table rows across chunk borders. This degrades retrieval precision and breaks citation accuracy.

## Decision
We implement a structure-aware chunking pipeline (`indexer/pipeline/chunk.py`) that:
1. Detects section and clause headings (e.g., `## 1. Attendance`, `5.4 Academic Warning`) and carries the current section identifier in every chunk's metadata.
2. Splits text cleanly along paragraph boundaries (`\n\n`), accumulating paragraphs up to a target size window (`CHUNK_SIZE=400` words/tokens).
3. Applies a sliding token overlap (`CHUNK_OVERLAP=50`) between consecutive chunks within a page to preserve cross-boundary context.
4. Generates deterministic, stable chunk IDs based on `source`, `page`, `chunk_index`, and content prefix.

## Options Considered
1. **Fixed-Size Token Windowing (e.g., 500 characters, no overlap):** Rejected because it frequently truncates sentences mid-rule and isolates section headings from their bodies.
2. **Page-Level Chunking:** Rejected because whole pages (often 800+ words) exceed effective dense embedding model context windows and inject noise into retrieval scoring.
3. **Structure-Aware Section & Paragraph Chunking (Chosen):** Balances semantic integrity with token length constraints, maximizing recall@5 and citation validity.

## Consequences
- **Positive:** Chunks retain natural clause context, allowing accurate citation attribution (`source`, `section`, `page`).
- **Positive:** Overlap prevents query failure on sentences that span chunk boundaries.
- **Trade-off:** Overlap introduces minor storage amplification in ChromaDB (~15% vector count increase), which is negligible for our corpus size.
