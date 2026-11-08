# ADR 0001: Run Indexer as a Kubernetes Batch Job

## Status
Accepted · 2026-11-08

## Context
In retrieval-augmented generation systems, document ingestion (extracting text, running OCR, computing chunk embeddings, and writing to ChromaDB) is a compute-intensive, batch-oriented workload. In contrast, the query API process is an interactive, low-latency, stateless service that reads from the vector store.
If indexing logic is embedded inside the API container lifecycle (e.g. at process startup):
1. Pod horizontal scaling triggers redundant, concurrent re-indexing passes that contend for write locks and overload ChromaDB.
2. Indexing a multi-hundred page document set takes minutes and consumes hundreds of megabytes of RAM, causing startup/readiness probes to fail and crash-looping API pods.
3. Multiple API replicas cannot independently guarantee atomicity or consistent metadata during embedding model transitions.

## Decision
We decouple document ingestion from query serving by running the indexer as an isolated Kubernetes batch `Job` (triggered manually via `make index`) and a recurring `CronJob` (`reindex`, scheduled weekly at `0 0 * * 0`).
The API deployment contains zero indexing code and only queries ChromaDB through read-only calls.

## Options Considered
1. **Index on API Pod Startup:** Rejected because each replica would trigger full re-indexing, wasting CPU/RAM and failing zero-downtime rolling updates.
2. **Dedicated Long-Running Ingestion Daemon:** Rejected because university corpus updates happen infrequently (semester or annual cycles). Maintaining an active daemon wastes cluster resources.
3. **Indexer as Kubernetes Job / CronJob (Chosen):** Indexer runs in an ephemeral pod with dedicated resource limits (1000m CPU, 1024Mi memory) and exits cleanly (exit code 0).

## Consequences
- **Positive:** API pods remain lightweight, fast-booting (<2s startup), and horizontally scalable via HPA without triggering vector writes.
- **Positive:** Job retries and failures are natively isolated by Kubernetes `backoffLimit: 3` without impacting user availability.
- **Trade-off:** Newly fetched documents are not immediately searchable until an indexer Job execution completes.
