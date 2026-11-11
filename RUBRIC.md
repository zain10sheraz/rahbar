# Rahbar – Assignment Rubric & Completion Status

## 0 · Starter Kit Cleanup
| Item | Status |
|------|--------|
| All starter placeholders and TODO markers removed | Done |
| All raise NotImplementedError removed | Done |

---

## 1 · API Layer
| Item | Status |
|------|--------|
| ChromaRetriever.retrieve implemented | Done |
| Ollama LLM provider implemented | Done |
| Hosted LLM provider implemented | Done |
| Redis-backed semantic cache implemented | Done |
| Relevance floor + abstention logic | Done |
| Citation check | Done |
| /readyz endpoint (Chroma, Redis, embedding-pin check) | Done |
| /healthz liveness endpoint | Done |
| /metrics Prometheus endpoint | Done |
| POST /api/ask working end-to-end | Done |

---

## 2 · Indexer Pipeline
| Stage | Status |
|-------|--------|
| extract.py - PDF/text extraction | Done |
| clean.py - text normalisation | Done |
| chunk.py - chunking with configurable size/overlap | Done |
| embed.py - embedding via Ollama | Done |
| store.py - writing chunks to Chroma | Done |

---

## 3 · Corpus
| Item | Status |
|------|--------|
| corpus/sources.yaml populated | Done |
| corpus/MANIFEST.md committed | Done |
| Documents fetched and verified | Done |

---

## 4 · Kubernetes and Infrastructure
| Item | Status |
|------|--------|
| api/Dockerfile | Done |
| indexer/Dockerfile | Done |
| ui/Dockerfile | Done |
| k8s/base/namespace.yaml | Done |
| k8s/base/configmap.yaml | Done |
| k8s/base/api.yaml (Deployment + Service) | Done |
| k8s/base/indexer-job.yaml (Kubernetes Job) | Done |
| k8s/base/chroma-statefulset.yaml (StatefulSet + PVC) | Done |
| k8s/base/redis.yaml | Done |
| k8s/base/ui.yaml | Done |
| k8s/base/ingress.yaml | Done |
| k8s/base/hpa.yaml (HorizontalPodAutoscaler) | Done |
| k8s/base/networkpolicy.yaml | Done |
| k8s/base/serviceaccounts.yaml | Done |
| k8s/overlays/dev/kustomization.yaml | Done |
| k8s/overlays/prod/kustomization.yaml | Done |
| Embedding-pin check | Done |

---

## 5 · CI and CD
| Item | Status |
|------|--------|
| .github/workflows/ci.yml - runs tests on dev push | Done |
| .github/workflows/cd.yml - deploys to Minikube on dev push | Done |
| Branch protection on main (no direct push) | Done |
| All work on dev branch, merged to main via PR | Done |

---

## 6 · Evaluation
| Item | Status |
|------|--------|
| eval/golden.yaml - 15+ questions | Done |
| recall_at_k implemented | Done |
| citation_validity implemented | Done |
| summarise implemented | Done |
| gate implemented | Done |
| eval/baseline.json committed | Done |

---

## 7 · Documentation
| Item | Status |
|------|--------|
| README.md with problem statement | Partial - diagram and CI badge still needed |
| docs/CORPUS.md | Done |
| docs/adr/0001-indexer-as-job.md | Done |
| docs/adr/0002-chunking-strategy.md | Done |
| docs/adr/0003-redis-cache-store.md | Done |
| docs/adr/0004-llm-provider-pii.md | Done |
| Evidence files (branch protection, HPA, endpoints, etc.) | Done |

---

## 8 · What Is Still Left
1. README polish - add architecture diagram and CI badge.
2. Wire SemanticCache into answer.py.
3. Extended integration tests (end-to-end pipeline).
4. Production overlay - Helm, TLS, secrets management.

---

Last updated: 2026-11-08
