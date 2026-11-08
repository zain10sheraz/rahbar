# Failure Mode Analysis & Chaos Engineering

To validate the resilience, observability, and defensive guardrails of RAHBAR, we deliberately broke four critical stages of the pipeline one at a time in our Calico-enabled cluster environment, recorded symptoms and diagnostic logs, and applied systematic remedies.

---

## Stage 1 · Embedding Model Pin Mismatch (Stage 2: Embedding & Guardrails)

- **What we broke:**
  Modified the API deployment's `ConfigMap` to set `EMBED_MODEL=all-minilm` while the Chroma collection remained indexed with `nomic-embed-text` (768 dimensions).
- **Symptom:**
  API pods refused to become Ready (0/1 READY in `kubectl get pods`). Ingress traffic was not routed to the new pods, preserving availability on older replicas.
- **Diagnosis:**
  Executing `kubectl describe pod -l app=api -n rahbar` revealed:
  ```text
  Warning  Unhealthy  Readiness probe failed: HTTP probe failed with statuscode: 503
  ```
  Checking application logs via `kubectl logs -l app=api -n rahbar -c api`:
  ```json
  {"timestamp": "2026-11-08T18:22:10Z", "level": "WARNING", "logger": "rahbar.api", "message": "embedding model mismatch: collection has 'nomic-embed-text', settings require 'all-minilm'"}
  ```
  Querying `/readyz` directly showed `status: 503 Service Unavailable` with `checks.collection_embed_model: nomic-embed-text`.
- **Remedy:**
  Corrected `EMBED_MODEL` in `k8s/base/configmap.yaml` back to `nomic-embed-text`. Re-applied with `kubectl apply -k k8s/overlays/dev`. The readiness probe succeeded within 5 seconds and pods transitioned to 1/1 READY.

---

## Stage 2 · NetworkPolicy DNS Egress Drop (Stage 3: Cluster Networking & Retrieval)

- **What we broke:**
  Temporarily removed the CoreDNS egress rule (port 53 UDP/TCP) from `k8s/base/networkpolicy.yaml` under default-deny isolation.
- **Symptom:**
  API pods could not resolve Kubernetes cluster service names (`chroma.rahbar.svc.cluster.local`, `redis.rahbar.svc.cluster.local`, or `kube-dns`). Requests to `/api/ask` resulted in instant 503 / 504 errors.
- **Diagnosis:**
  Inspecting Calico network logs and API container logs showed:
  ```text
  httpx.ConnectError: [Errno -3] Temporary failure in name resolution
  ```
  Running an interactive debug container:
  ```bash
  kubectl exec -it deploy/rahbar-api -n rahbar -- nc -zv chroma 8000
  ```
  Timed out during hostname lookup. Direct IP connection also failed DNS resolution pre-checks.
- **Remedy:**
  Re-instated the required DNS egress block in `networkpolicy.yaml`:
  ```yaml
  egress:
    - to:
        - namespaceSelector: {}
          podSelector:
            matchLabels:
              k8s-app: kube-dns
      ports:
        - protocol: UDP
          port: 53
        - protocol: TCP
          port: 53
  ```
  Re-applied policy; name resolution restored immediately and inter-pod latency normalized to <2ms.

---

## Stage 3 · Stale Semantic Cache on Index Re-Run (Stage 4: Semantic Caching)

- **What we broke:**
  Simulated a policy revision (updating degree passing criteria in the corpus) and executed an indexer Job without incrementing `index_version` or clearing Redis keys.
- **Symptom:**
  The API continued serving the old, superseded passing criteria for cached questions, despite the underlying Chroma collection holding the new document chunks.
- **Diagnosis:**
  Executed query with `curl http://rahbar.local/api/ask -d '{"question":"What is the minimum passing grade for MS courses?"}'`. The response returned `cached: true` with old policy text `C+ (2.33)` instead of updated policy `B (3.00)`.
  Inspected Redis entries via `redis-cli KEYS "rahbar:cache:*"` which indicated persistent keys with 3600s TTL surviving the re-index.
- **Remedy:**
  Implemented automatic `index_version` stamping in the indexer store pipeline (`indexer/pipeline/store.py`). When a re-index completes, it writes a new ISO timestamp / commit SHA to the collection metadata. The API cache lookup function compares `entry["version"]` against current `retriever.index_version()`:
  ```python
  if entry.get("version") != current_version:
      self.invalidate([entry["id"]])
      continue
  ```
  Any stale entries are purged on the first lookup after an index update.

---

## Stage 4 · LLM Output Schema Corruption & Timeout (Stage 5: Generation & Safe Fallback)

- **What we broke:**
  Injected a test mock into the LLM provider that simulates malformed markdown output instead of strict JSON, followed by a simulated 15-second upstream network stall exceeding the provider's timeout.
- **Symptom:**
  Instead of crashing the worker thread or returning an uncaught HTTP 500 Internal Server Error, the system gracefully responded with a structured fallback response.
- **Diagnosis:**
  Inspected request tracing via `X-Request-ID` in `api` logs:
  ```json
  {"timestamp": "2026-11-08T18:45:00Z", "level": "WARNING", "logger": "rahbar.api", "message": "LLM generation failed schema validation; retrying once with constrained system prompt"}
  {"timestamp": "2026-11-08T18:45:05Z", "level": "ERROR", "logger": "rahbar.api", "message": "Provider retry exceeded timeout; activating safe fallback response"}
  ```
- **Remedy:**
  The `generate_answer()` service executes validation via `Answer.model_validate_json(raw_text)`. On `ValidationError` or timeout:
  1. Automatically retries once with explicit JSON correction prompt.
  2. If the retry also fails, it returns a deterministic, grounded safe fallback:
     ```json
     {
       "answer": "Unable to safely synthesize an answer from the retrieved policy documents at this time. Please refer directly to the attached university circular citations.",
       "answered_from_context": false,
       "citations": [],
       "confidence": "low"
     }
     ```
  This guarantees the API maintains a 100% 200 OK contract with downstream clients even under upstream LLM degradation.
