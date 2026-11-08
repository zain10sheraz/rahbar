# Corpus Documentation

Source: FAST-NUCES public website (`https://nu.edu.pk`) · Documents: 9 · Total Pages: 279+

This corpus captures official university policies, handbooks, prospectuses, financial tables, and annual reports to benchmark the RAHBAR retrieval-augmented question answering system. All raw sources are tracked in `corpus/MANIFEST.md` with SHA-256 integrity checksums.

## Required Properties Mapping

| # | Required property | Document(s) that provide it | Evidence or notes |
| --- | --- | --- | --- |
| 1 | At least 6 documents, 40 pages | 9 documents total: 7 PDFs and 2 HTML files (`academic-rules-handbook-jun-2026.pdf` [58 pp], `annual-report-2023-24.pdf` [85 pp], `student-handbook-jun-2026.pdf` [64 pp], `undergraduate-academic-rules-aug-2023.pdf` [26 pp], `annual-report-2019-20.pdf` [33 pp], `faculty-entrepreneurship-and-technical-start-ups-policy.pdf` [8 pp], `prospectus-2026-academic-rules-and-regulations.pdf` [5 pp]) | Total PDF pages exceed 279 pages, comfortably meeting the requirement. |
| 2 | Two versions of one policy | `undergraduate-academic-rules-aug-2023.pdf` (doc_version `2023-08`, superseded: `true`) vs `academic-rules-handbook-jun-2026.pdf` (doc_version `2026-06`, superseded: `false`) | The 2026 edition supersedes the 2023 rules. Chunk metadata stores `doc_version` and boolean `superseded`, enabling the retrieval layer to filter out superseded clauses so students receive only active policy. |
| 3 | Scanned, image-only PDF | `faculty-entrepreneurship-and-technical-start-ups-policy.pdf` (8 pages) | Running `pdffonts corpus/raw/faculty-entrepreneurship-and-technical-start-ups-policy.pdf` returns an empty font table, proving the PDF contains scanned bitmap page images without an embedded text layer. Handled via `pdf2image` and `pytesseract` OCR extraction. |
| 4 | A table with real information | `fee-structure-page.html`, `grading-page.html`, `annual-report-2023-24.pdf` | The Fee Structure page includes tabular tuition fees per credit hour, admission fees, and security deposits. The Grading page defines grade-point conversion tables (letter grade, grade points, percentage bands). `pdfplumber` extracts tables into pipe-delimited text representations. |
| 5 | Long definitions | `student-handbook-jun-2026.pdf` and `academic-rules-handbook-jun-2026.pdf` | Detailed multi-paragraph definitions of Academic Dishonesty (plagiarism, unauthorized collaboration, fabrication), Disciplinary Committee proceedings, and Warning/Probation statuses. |
| 6 | A deliberately absent topic | Hostel & On-Campus Residential Facilities | Transport and Hostel regulations (`Transport and Hostel Facilities.pdf`) were deliberately omitted from `corpus/sources.yaml`. Students frequently ask about hostel allotment and fee refund policies, allowing RAHBAR to be benchmarked on honest abstention (`must_abstain: true`). |
| 7 | Exact-term content | `academic-rules-handbook-jun-2026.pdf`, `grading-page.html`, `fee-structure-page.html` | Specific clause references (Clause 1.21 for 80% attendance requirement, Clause 5.4 for CGPA 2.00 academic warning threshold, course repetition regulations, and exact tuition fees). |

## Ingestion Pipeline Summary
- Extraction: Managed by `indexer/pipeline/extract.py` using `pdfplumber`, `pypdf`, `pytesseract` for OCR on scanned pages, and HTML clean extraction.
- Cleaning: `indexer/pipeline/clean.py` strips repetitive running headers and footers while preserving section hierarchy and clause numbers.
- Chunking: `indexer/pipeline/chunk.py` maintains structure awareness and metadata (`source`, `section`, `page`, `doc_version`, `superseded`).
