# RAHBAR: Grounded Institutional RAG on Kubernetes

[![CI](https://github.com/zain10sheraz/rahbar/actions/workflows/ci.yml/badge.svg)](https://github.com/zain10sheraz/rahbar/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.12](https://img.shields.io/badge/Python-3.12-brightgreen.svg)](https://www.python.org/)
[![Kubernetes: v1.30+](https://img.shields.io/badge/Kubernetes-v1.30+-326ce5.svg)](https://kubernetes.io/)

RAHBAR is a production-grade, grounded Retrieval-Augmented Generation (RAG) microservice running on Kubernetes. It indexes authoritative university regulations, HEC policies, degree roadmaps, and examination rules to provide verified, hallucination-free answers with verifiable chunk-level citations.

---

## Architecture Overview

```mermaid
graph TD
    Client[User Browser / Client] -->|HTTP / Ingress| Ingress[Kubernetes Ingress (rahbar.local)]
    Ingress -->|/| UI[Nginx UI Pod (port 80)]
    Ingress -->|/api/*| API[FastAPI API Replicas (HPA 3-10)]

    subgraph Internal Namespace: rahbar [Namespace: rahbar (Zero-Trust Calico NetworkPolicy)]
        API -->|Cache Lookup / Store (Cosine Sim)| Redis[(Redis Semantic Cache)]
        API -->|Vector Similarity Query| Chroma[(ChromaDB StatefulSet)]
        API -->|HTTP 53| DNS[kube-dns]
        Cron[CronJob / Manual Trigger] --> Job[Indexer Batch Job]
        Job -->|OCR & Chunk Upsert| Chroma
    end

    subgraph Host / External Inference
        API -->|Embed Query (nomic-embed-text)| Ollama[Host Ollama / Hosted LLM]
        Job -->|Embed Batch| Ollama
        API -->|Constrained JSON Synthesis| LLM[Ollama Llama3 / Hosted LLM]
    end
```

---

## Key Features

1. **Strict Groundedness & Zero Hallucination:** 
   - Every answer is validated with Pydantic against the retrieved context. If relevance scores fall below floor ($0.70$) or context is absent, the system explicitly abstains (`answered_from_context: false`).
   - Every citation is validated against chunk IDs actually retrieved from Chroma. Fabricated citations trigger rejection.
2. **Decoupled Job-Based Indexing:**
   - Vector indexing runs strictly as an asynchronous Kubernetes `Job` or scheduled `CronJob`. The API process contains zero indexing code, eliminating write-lock contention across replicas.
3. **Embedding Model Pinning & Startup Guardrail:**
   - The indexer stamps its model (`nomic-embed-text`) into the Chroma collection metadata. If an operator changes `EMBED_MODEL` on the API without re-indexing, `/readyz` fails with HTTP 503, preventing corrupted vector comparisons.
4. **Redis-Backed Semantic Cache:**
   - Caches semantically equivalent questions using cosine similarity threshold ($0.88$). Invalides entries automatically when the collection's `index_version` changes. Follow-ups and abstentions are never cached.
5. **Zero-Trust Network Hardening:**
   - Enforces default-deny NetworkPolicies across ingress and egress. UI pods cannot communicate directly with Chroma or Redis. All containers run as unprivileged rootless users with read-only root filesystems.

---

## API Specification

| Method | Endpoint | Description | Success Code | Error Codes |
| :--- | :--- | :--- | :--- | :--- |
| GET | `/healthz` | Process liveness probe. Touches zero dependencies. | 200 OK | 500 |
| GET | `/readyz` | Readiness probe. Validates Chroma, Redis, and embedding model pin. | 200 OK | 503 Service Unavailable |
| GET | `/metrics` | Prometheus exposition endpoint for requests, latency, and cache hits. | 200 OK | 500 |
| POST | `/api/ask` | Submit natural language query. Returns grounded answer with citations. | 200 OK | 400, 422, 503 |

### Sample Request & Response
```bash
curl -X POST http://rahbar.local/api/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the minimum CGPA required to avoid academic probation?"}'
```

```json
{
  "answer": "A student must maintain a minimum Cumulative Grade Point Average (CGPA) of 2.00 to remain in good standing. Falling below 2.00 places the student on academic probation for the subsequent semester.",
  "answered_from_context": true,
  "citations": [
    {
      "source": "exam_rules.pdf",
      "section": "Section 4.1 Academic Standing",
      "page": 7,
      "chunk_id": "exam_rules_c14"
    }
  ],
  "confidence": "high",
  "cached": false,
  "request_id": "f8a12b4e93d142cb"
}
```

---

## Cluster Setup & Deployment Guide

### Prerequisites
- Docker, Minikube (or Kind), `kubectl`, `kustomize`, `helm`.
- Ollama running on host with `nomic-embed-text` pulled (`ollama pull nomic-embed-text`).

### 1. Cluster Provisioning (Calico CNI)
Start Minikube with Calico networking enabled and sufficient resources:
```bash
minikube start \
  --driver=docker \
  --cni=calico \
  --memory=4096 \
  --cpus=2

minikube addons enable ingress
minikube addons enable metrics-server
```

Add the domain mapping to your `/etc/hosts` (or `C:\Windows\System32\drivers\etc\hosts`):
```text
127.0.0.1 rahbar.local
```

### 2. The Exact Manifest Apply Order
Deploy the namespace, secrets template, storage, services, workloads, and network policies using Kustomize:
```bash
# Apply the complete dev overlay in order
kubectl apply -k k8s/overlays/dev

# Verify all deployments and statefulsets rollout cleanly
kubectl rollout status statefulset/chroma -n rahbar --timeout=120s
kubectl rollout status deployment/redis -n rahbar --timeout=60s
kubectl rollout status deployment/rahbar-api -n rahbar --timeout=120s
kubectl rollout status deployment/rahbar-ui -n rahbar --timeout=60s
```

### 3. How to Run the Indexer
The raw corpus documents are processed by the indexer batch Job:
```bash
# Trigger an immediate manual indexing run
kubectl create job --from=cronjob/rahbar-indexer indexer-manual-run -n rahbar

# Follow the indexing logs
kubectl logs -f job/indexer-manual-run -n rahbar -c indexer
```

---

## Local Development & Testing

Run unit and integration tests across both API and Indexer components:
```bash
# Run API test suite (31 tests covering cache, pins, citations, injection)
.venv/bin/pytest api/tests

# Run Indexer test suite
.venv/bin/pytest indexer/tests

# Run end-to-end evaluation benchmark
python3 eval/run_eval.py --api http://rahbar.local --golden eval/golden.yaml
```

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
