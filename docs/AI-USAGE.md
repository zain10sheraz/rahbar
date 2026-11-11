# AI Usage Disclosure

In accordance with course guidelines, this document provides an honest and complete disclosure of all AI tools used during the design, development, debugging, and documentation of Project RAHBAR.

| Tool | What it wrote or shaped | What we changed afterwards, and why |
| --- | --- | --- |
| **Google Antigravity (Gemini 2.5 / Claude 3.5 Sonnet)** | Initial scaffolding of FastAPI endpoints, Pydantic schemas, and retrieval interfaces. | Hand-edited the citation validation logic and relevance floor calculation to ensure strict adherence to chunk-level IDs and prevent hallucinations. Added explicit typing and error handlers. |
| **Google Antigravity** | Redis semantic cache backend (`api/app/services/cache.py`) with cosine similarity lookup and TTL. | Implemented never-cache rules for follow-up questions and low-confidence abstentions. Added collection `index_version` cache invalidation so re-indexing drops stale cached answers. |
| **Google Antigravity** | Kubernetes YAML manifests for Chroma StatefulSet, Redis, API, UI, Indexer Job, CronJob, HPA, and NetworkPolicies. | Fixed DNS egress on UDP/TCP port 53 for default-deny NetworkPolicies. Added explicit `runAsNonRoot: true`, `readOnlyRootFilesystem: true`, and dropped capabilities. Verified resource requests and limits to ensure HPA metrics compute without `<unknown>`. |
| **Google Antigravity** | Evaluation runner (`eval/run_eval.py`) and golden evaluation dataset (`eval/golden.yaml`). | Validated ground-truth targets against real ITU and university policy documents. Wrote exact-term, version-sensitive, and prompt-injection test cases. Gated CI exit codes on recall@5 and citation validity. |
| **Google Antigravity** | GitHub Actions CI/CD workflows (`ci.yml` and `cd.yml`). | Added kubeconform linting, Trivy vulnerability scanners, least-privilege `permissions:` blocks, Docker Hub SHA tagging, and `kubectl rollout status` verification steps. |
| **Google Antigravity** | Architectural Decision Records (ADR 0001 to 0004) and failure mode analysis. | Refined ADR 0001 into first-person engineering voice reflecting team constraints, trade-offs between Chroma StatefulSet vs ephemeral DB, and Calico CNI networking decisions. |
