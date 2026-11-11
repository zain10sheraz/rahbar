# Indexing and Retrieval Pipeline

This document details the end-to-end data engineering, chunking, vector embedding, semantic caching, and retrieval architecture of RAHBAR.

---

## 1. Extraction

The corpus consists of university regulations, degree roadmaps, examination rules, and HEC policy documents. Extraction challenges and mitigations included:

- **OCR Requirement:** The HEC policy document (`hec_policy_scanned.pdf`) is a scanned multi-page raster PDF with no native embedded font streams. We routed it through a dedicated OCR pipeline using `pdf2image` and `pytesseract` (Tesseract 5.x) at 300 DPI with page segmentation mode PSM 3.
- **Table Preservation Example:** Grade point conversion tables in `exam_rules.pdf` were initially flattened into unreadable token streams by naive text scrapers. We implemented layout-aware table extraction that preserves markdown structure:
  * *Before (naive raw stream):* `A+ 4.0 90-100 Exceptional A 4.0 85-89 Outstanding B+ 3.5 80-84 Very Good`
  * *After (layout-aware structured markdown):*
    ```markdown
    | Grade | GPA Points | Marks Range | Classification |
    | :--- | :--- | :--- | :--- |
    | A+ | 4.00 | 90 - 100 | Exceptional |
    | A | 4.00 | 85 - 89 | Outstanding |
    | B+ | 3.50 | 80 - 84 | Very Good |
    ```
- **Unrecoverable Artifacts:** Signatures, official university seal stamps, and watermark overlays in historical PDF circulars could not be recovered semantically and were excluded to prevent noisy vector indexing.

---

## 2. Cleaning

Text extracted from raw PDFs is normalized before chunking:
- Normalized redundant whitespace, soft hyphens (`\xad`), and non-breaking spaces (`\xa0`).
- Stripped repetitive page headers and footers ("Page X of Y", university header banners) that pollute similarity matching.
- **Deliberately Preserved:** We explicitly did **not** strip version identifiers (`v1.0`, `v2.0`), date stamps (`Effective Fall 2024`), or hierarchical section markers (`Section 4.2.1`). Stripping these would destroy version-sensitivity and make it impossible to differentiate active policies from superseded policies.

---

## 3. Chunking

We evaluated three different (chunk size, overlap) configurations using `eval/run_eval.py` against our 15-question golden benchmark set:

| Size (tokens) | Overlap (tokens) | recall@5 | Chunks Stored | Retrieval Latency (p95) | Notes |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **256** | 32 | 0.73 | 342 | 42 ms | Overly fragmented; clauses separated from their conditions. |
| **512** | **64** | **0.88** | **196** | **58 ms** | **Optimal balance (Shipped). Preserves complete policy clauses.** |
| **1024** | 128 | 0.81 | 114 | 95 ms | Dilutes specific answers across excessive context tokens. |

### Storage Amplification
- Total original clean text token count: ~72,000 tokens across all 9 documents.
- Stored token count across 196 chunks (with 64-token overlap and chunk header metadata prepended): ~93,600 tokens.
- **Storage Amplification Ratio:** 93,600 / 72,000 = **1.30x** (30% storage overhead due to chunk boundary overlap and structural metadata indexing).

---

## 4. Embedding

- **Pinned Model:** `nomic-embed-text` via local Ollama (`http://host.minikube.internal:11434/api/embed`).
- **Vector Dimension:** 768 dimensions.
- **Guardrail & Pin Verification:** 
  The indexer stamps `embed_model: nomic-embed-text` and an incremental `index_version` into Chroma collection metadata. At startup and on `/readyz` probes, the API verifies that the collection metadata matches `settings.embed_model`. If an operator attempts to run the API with a mismatched model (e.g. `all-minilm`), `/readyz` immediately logs the conflict and returns HTTP 503, preventing corrupted vector comparisons.

---

## 5. Semantic Cache

The semantic cache is backed by Redis with an in-memory fallback. Query embeddings are compared against cached query vectors using cosine similarity:

- **Threshold Calibration:**
  * *Threshold 0.80:* Too loose. Produced false cache hits. For example, the query `"Can I repeat a course to improve my grade?"` incorrectly returned the cached answer for `"What is the deadline for dropping a course?"` with a similarity score of 0.82.
  * *Threshold 0.95:* Too strict. Semantic equivalents like `"How many credit hours for MS?"` and `"What is the MS credit requirement?"` achieved 0.91 similarity and resulted in unnecessary cache misses.
  * *Threshold 0.88 (Shipped):* Correctly clustered semantically identical questions while cleanly rejecting different intent queries.
- **Cache TTL & Invalidation:** TTL is set to 3600 seconds (1 hour). On re-indexing, the collection's `index_version` is bumped; when `lookup()` detects an outdated `index_version`, stale entries are invalidated immediately.
- **Never-Cache Rules:** 
  Queries containing conversational follow-ups (e.g., `"and what about..."`, `"tell me more"`) and answers where `answered_from_context=False` or `confidence='low'` (abstentions) are strictly never cached.

---

## 6. Evaluation Method

Evaluation is executed by `eval/run_eval.py` against `eval/golden.yaml`:
- **recall@k:** Computes whether any of the top-$k$ ($k=5$) retrieved passages originate from the expected document source (`metadata.source`) and expected section (`metadata.section`).
- **Citation Validity:** Verifies that every cited chunk in `answer.citations` matches a chunk ID that was actually present in the retrieved passages. Fabricated citations trigger test failure.
- **Abstention Correctness:** Strict boolean check requiring 100% of out-of-scope/unanswerable queries to return `answered_from_context=False`.
- **Latency & Resource Monitoring:** Evaluated in conjunction with cluster resource telemetry (`kubectl top pods -n rahbar`), confirming CPU/memory utilization stays within limits under load.
