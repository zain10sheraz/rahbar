# ADR 0003 – Redis‑backed semantic cache

## Context
The answer service repeatedly receives identical questions. Re‑computing the retrieval + generation pipeline for every request is wasteful.

## Decision
Introduce a lightweight cache layer:
* Uses the  Python client when  is set.
* Falls back to an in‑memory dictionary for local development.
* Stores the full  JSON payload keyed by the raw question.
* TTL is configurable via  (default 300 s).

## Consequences
* Cache hits skip the expensive retrieval/generation steps.
* Cache miss behavior is unchanged.
* Adding the cache does not affect the existing API contract.
