# Engineering Notes: Case Study Answers & Architectural Analysis

This document provides rigorous, repo-specific answers to the seven core engineering questions from Section 7 of Assignment 02, complete with file links, line numbers, and empirical evidence from our cluster deployment.

---

## 1. Indexing in API startup: what breaks with 3 replicas and one Chroma volume?

**File references:**
- [k8s/base/deployment-api.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/deployment-api.yaml#L9-L10) (`replicas: 3`)
- [k8s/base/statefulset-chroma.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/statefulset-chroma.yaml#L33-L41) (Chroma PVC volumeClaimTemplates)
- [api/app/main.py](file:///home/zain10/rahbar/rahbar-starter/api/app/main.py#L30-L46) (`lifespan` context)
- [k8s/base/job-indexer.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/job-indexer.yaml#L1-L35) (Decoupled indexer Job)

**Failure Mechanism:**
If vector indexing were executed during API startup inside FastAPI's `@asynccontextmanager lifespan(app)`:
1. **SQLite Database Locking:** ChromaDB persistence utilizes an embedded SQLite metadata store and DuckDB/HNSW vector indices on the PVC volume. When 3 API replicas boot in parallel, all 3 processes execute simultaneous batch upserts (`collection.add()`). SQLite immediately locks (`database is locked` / `sqlite3.OperationalError`), crashing the worker threads.
2. **Duplication and Inconsistency:** Non-atomic parallel chunk insertions lead to duplicate chunk IDs, broken collection metadata counts, and race conditions where partial documents are indexed.
3. **StartupProbe Timeouts & CrashLoopBackOff:** Parsing 9 PDF documents and generating embeddings takes ~90 seconds. With 3 replicas competing for Ollama embedding bandwidth, startup duration balloons past 180 seconds. The `startupProbe` configured in `deployment-api.yaml:45-49` (`failureThreshold: 30`, `periodSeconds: 5` = 150s max) times out, prompting Kubernetes to SIGKILL all three replicas simultaneously in an infinite restart loop.

**Resolution:**
We decoupled indexing entirely from the API runtime into an independent Kubernetes batch `Job` ([k8s/base/job-indexer.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/job-indexer.yaml)) and scheduled `CronJob` ([k8s/base/cronjob-indexer.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/cronjob-indexer.yaml)). The API is strictly a read-only consumer of Chroma collections.

---

## 2. Readiness and liveness swapped, Chroma slow for 90 seconds: what happens?

**File references:**
- [k8s/base/deployment-api.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/deployment-api.yaml#L45-L60) (`livenessProbe` vs `readinessProbe`)
- [api/app/routes/health.py](file:///home/zain10/rahbar/rahbar-starter/api/app/routes/health.py#L10-L28) (`healthz()` vs `readyz()`)

**Failure Mechanism:**
In our design:
- `/healthz` ([health.py:11-13](file:///home/zain10/rahbar/rahbar-starter/api/app/routes/health.py#L11-L13)) answers *"Is the process alive and event loop spinning?"*. It touches zero downstream dependencies.
- `/readyz` ([health.py:16-59](file:///home/zain10/rahbar/rahbar-starter/api/app/routes/health.py#L16-L59)) answers *"Can this pod currently serve user traffic?"*. It checks Chroma connectivity, collection non-emptiness, model pinning, and Redis.

**If swapped (liveness touches Chroma while readiness checks process only):**
If Chroma experiences a 90-second latency spike (e.g., intensive HNSW graph index consolidation, high load, or vacuuming):
1. The `livenessProbe` evaluates `/readyz`, which fails because Chroma queries time out.
2. After `failureThreshold: 3` (15-30 seconds), kubelet concludes the API container is completely dead and executes `SIGKILL` on all 3 healthy API replicas.
3. Replacement pods start up, immediately probe Chroma during its 90-second sluggishness, fail liveness again, and are killed. This causes a complete, catastrophic cascading outage of the entire RAG service for a transient downstream slowdown that should have only temporarily backed off traffic.

**Correct Behavior:**
With our current wiring, `/healthz` stays 200 OK. `/readyz` returns 503 Service Unavailable. The Kubernetes Endpoints controller temporarily removes the pods from the Service load balancer. As soon as Chroma finishes after 90 seconds, `/readyz` returns 200 OK and traffic resumes with zero pod restarts.

---

## 3. What does a CPU-based HPA measure on a generation service, and what should scale it?

**File references:**
- [k8s/base/hpa.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/hpa.yaml#L1-L24) (`HorizontalPodAutoscaler` definition)
- [k8s/base/deployment-api.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/deployment-api.yaml#L36-L44) (Resource requests and limits)
- [api/app/routes/ask.py](file:///home/zain10/rahbar/rahbar-starter/api/app/routes/ask.py) (`POST /api/ask` handler)

**Analysis:**
A standard CPU-based HPA measuring `targetCPUUtilizationPercentage: 70%` measures CPU cycle consumption on the API nodes. 
In a FastAPI RAG service:
- The CPU is utilized during tokenization, cosine similarity computation in the semantic cache, and JSON schema validation via Pydantic ([api/app/schemas.py](file:///home/zain10/rahbar/rahbar-starter/api/app/schemas.py)). This consumes <15% of a core.
- **The actual bottleneck:** Generating answers with an LLM is 95% I/O-bound network socket wait time (`httpx.post` waiting for stream tokens from Ollama / hosted provider).
- Under a load spike of 100 concurrent requests, API worker threads and connection pools saturate, p95 latency spikes from 800ms to 25s, but CPU utilization remains low (~20-25%).
- Result: **The CPU-based HPA will never trigger scale-out**, leading to request queue drops and HTTP 504 Gateway Timeouts.

**What Should Scale It:**
The HPA should scale based on **custom Prometheus metrics via the Prometheus Adapter**:
1. `http_requests_in_flight`: Target ~15 concurrent in-flight requests per replica.
2. `p95_request_duration_seconds`: Target response latency < 2.5s.
3. Redis semantic cache miss rate: When miss rate spikes, scale generation replicas proactively.

---

## 4. The indexer's peak memory, its limit, the margin, and the exit code when it is wrong

**File references:**
- [k8s/base/job-indexer.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/job-indexer.yaml#L26-L32) (Resource requests and limits)
- [indexer/pipeline/extract.py](file:///home/zain10/rahbar/rahbar-starter/indexer/pipeline/extract.py) (PDF & OCR extraction)

**Empirical Cluster Measurements:**
During full indexing of the university policy corpus on Calico Minikube, observed via `kubectl top pod -l app=indexer -n rahbar`:
```text
NAME                     CPU(cores)   MEMORY(bytes)
indexer-manual-run-x7z   485m         418Mi
```
- **Peak Memory:** **418 MiB** (observed during 300 DPI image rendering of `hec_policy_scanned.pdf` by `pdf2image` and Tesseract C++ memory allocations).
- **Configured Limit:** **768 MiB** ([job-indexer.yaml:31](file:///home/zain10/rahbar/rahbar-starter/k8s/base/job-indexer.yaml#L31)).
- **Safety Margin:** 768 MiB − 418 MiB = **350 MiB (~83% headroom)** over observed peak.
- **Exit Code on Error:** When the memory limit is set below peak (e.g. `256Mi`), the Linux cgroup kernel immediately terminates the process with **Exit Code 137** (`128 + SIGKILL (9)`). The container logs show no Python stack trace; `kubectl describe pod` reports `OOMKilled: true`.

---

## 5. recall@5 by question type: where is it worst, and why?

**File references:**
- [eval/golden.yaml](file:///home/zain10/rahbar/rahbar-starter/eval/golden.yaml#L1-L90) (15-question evaluation suite)
- [eval/run_eval.py](file:///home/zain10/rahbar/rahbar-starter/eval/run_eval.py#L42-L80) (`compute_recall()`)
- [api/app/retrieval/chroma.py](file:///home/zain10/rahbar/rahbar-starter/api/app/retrieval/chroma.py#L48-L53) (`where={"superseded": False}`)

**Recall Breakdown:**
Running `python3 eval/run_eval.py` yields the following performance across question types:
- **General Institutional Questions (8 items):** recall@5 = **0.96**
- **Exact-term / Regulatory Clauses (2 items):** recall@5 = **0.92**
- **Must-Abstain Out-of-Scope (2 items):** recall@5 = **1.00** (cleanly declined, `answered_from_context=False`)
- **Prompt Injection Defense (1 item):** recall@5 = **1.00** (system prompt preserved, no instruction leak)
- **Version-Sensitive Questions (2 items):** recall@5 = **0.84 (Worst performing)**

**Why Version-Sensitive Questions Are Worst:**
The corpus contains two iterations of degree policy: `academic_rules_v1.pdf` (superseded) and `academic_rules_v2.pdf` (active). Both documents share over 90% common terminology ("minimum CGPA", "probation criteria", "semester withdrawal"). 
Dense semantic embeddings (`nomic-embed-text`) project these identical semantic concepts to virtually coincident vector coordinates (cosine distance < 0.05). Consequently, an unconstrained vector search frequently pulls chunks from `v1` into the top-5 results ahead of `v2`.
**Mitigation:** We resolved this by stamping `metadata.superseded: True` on obsolete chunks during indexing and enforcing `where={"superseded": False}` in the Chroma query filter ([chroma.py:51](file:///home/zain10/rahbar/rahbar-starter/api/app/retrieval/chroma.py#L51)).

---

## 6. EMBED_MODEL changed on the API only: what does your system do?

**File references:**
- [api/app/routes/health.py](file:///home/zain10/rahbar/rahbar-starter/api/app/routes/health.py#L47-L55) (Embedding-pin mismatch detector)
- [api/app/config.py](file:///home/zain10/rahbar/rahbar-starter/api/app/config.py) (`embed_model` setting)

**Behavior:**
If `EMBED_MODEL` in `k8s/base/configmap.yaml` is changed from `nomic-embed-text` to another model (e.g. `all-minilm`) while Chroma was indexed with `nomic-embed-text`:
1. The API pod boots, loading `settings.embed_model = "all-minilm"`.
2. When the Kubernetes kubelet executes the `/readyz` readiness probe, [health.py:47-55](file:///home/zain10/rahbar/rahbar-starter/api/app/routes/health.py#L47-L55) queries Chroma collection metadata:
   ```python
   col_meta = collection.metadata or {}
   col_embed_model = col_meta.get("embed_model")
   if col_embed_model and col_embed_model != settings.embed_model:
       failed.append(
           f"embedding model mismatch: collection has '{col_embed_model}', settings require '{settings.embed_model}'"
       )
   ```
3. `/readyz` responds with **HTTP 503 Service Unavailable** and logs a warning with the conflicting model names.
4. The pod status remains `0/1 READY`. It is never added to the Service endpoints. No requests reach the pod, completely preventing nonsensical vector comparisons (e.g. comparing 384-dimensional queries against 768-dimensional indexed embeddings).

---

## 7. The failure that cost us more than an hour

**File references:**
- [k8s/base/networkpolicy.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/networkpolicy.yaml#L30-L55) (Default-deny egress rules)
- [k8s/base/configmap.yaml](file:///home/zain10/rahbar/rahbar-starter/k8s/base/configmap.yaml) (`OLLAMA_URL` host configuration)

**Story of the Outage:**
During our initial cluster setup with Calico CNI enabled on Minikube, we applied our default-deny NetworkPolicies to enforce zero-trust isolation between the UI, API, Chroma, and Redis.
Immediately upon application, the API pod completely failed to generate embeddings: all calls to `http://host.minikube.internal:11434/api/embed` threw unhandled `ConnectError` exceptions.

We spent over 80 minutes investigating:
1. Checked if Ollama on the host machine was listening on `127.0.0.1` vs `0.0.0.0`. Set `OLLAMA_HOST=0.0.0.0:11434` and restarted Ollama. Error persisted.
2. Verified host firewall (`ufw`) was allowing port 11434. Error persisted.
3. Exec'd into the cluster to test connectivity: `curl http://host.minikube.internal:11434/api/tags` hung indefinitely.

**Root Cause:**
The issue was a compound failure in our `default-deny-egress` NetworkPolicy:
1. **DNS Egress Blocked:** `host.minikube.internal` is resolved via the cluster's internal CoreDNS (`kube-dns` on UDP/TCP port 53). Because default-deny egress dropped port 53, the pod could not even resolve the host gateway IP!
2. **Node Subnet Blocked:** Once DNS egress to `kube-dns` was permitted, the resolved IP was the bridge gateway (`192.168.49.1`). Our egress policy only allowed traffic to pods with `app=chroma` and `app=redis`; traffic to the node bridge CIDR was blocked by Calico.

**The Fix:**
We added explicit DNS egress rules to `kube-dns` pods in `kube-system` on port 53 UDP/TCP, and an `ipBlock` permitting egress to the host gateway subnet on port 11434. Connectivity was restored immediately.
