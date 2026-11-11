# RAHBAR: completion checklist and runbook

Written for the team, to answer two questions: **is it complete?** and **how do I run it and know it works?**
Status below is what was *verified by running or reading the code* on 8 Nov 2026 (evening). Anything marked `?` has not been verified yet. Re-tick boxes as you go.

Legend: `[x]` verified working, `[~]` exists but incomplete or unmerged, `[ ]` missing or failing, `[?]` not yet checked.

---

## 1. Status against the assignment

### 1.1 Repository and process (spec section 6, section 8)
- [~] `dev` and `main` exist. `main` must be protected (PR required, CI required, 1 approval). **Not verified**: check Settings, Branches.
- [ ] Work happens on feature branches with PRs (so far only `dev` to `main` merges existed).
- [ ] Commit count 35-40+ and each person's share (check with section 5.1 below).
- [ ] No secret anywhere in history (run the scan in section 5.2).
- [ ] `LICENSE` file present.

### 1.2 CI/CD (spec section 6)
- [ ] `ci.yml` triggers on pull request to `main` and push to `dev`. (Currently PR to `dev`.)
- [ ] Jobs: lint, test (>= 60% coverage), manifests (kubeconform), build, scan (Trivy), e2e-eval. (Currently only one `make test` job.)
- [ ] `cd.yml` runs on push to `main`: test, then build-push (Docker Hub, tag = commit SHA, `needs:`), then deploy (`needs:`, smoke test). (Currently triggers on `dev`, pushes nothing.)
- [ ] `permissions:` block in both workflows.
- [ ] A successful `cd.yml` run exists (this link is submitted).
- [ ] Screenshot of the blocked merge on a failing eval gate, then green.

### 1.3 Application (spec sections 3, 4.3, 4.4, 4.8)
- [x] Liveness `/healthz` touches no dependency. Readiness `/readyz` checks Chroma, non-empty collection, Redis, embedding model.
- [~] Semantic cache: cosine threshold, never-cache rules, re-index expiry. **On branch `feat/api-semantic-cache`, not merged yet.**
- [~] No silent embedding fallback in the API. **Same branch.** The indexer's `embed.py` still falls back silently to fake vectors (fix pending).
- [x] Startup embedding-pin check in `main.py` and guardrails in `/readyz` (section 4.4).
- [ ] Query pipeline: validate, retry once, canned fallback, abstain below the relevance floor, delimited retrieved text (prompt injection), citations restricted to retrieved chunks. `answer.py` implements about half of this.
- [ ] Metrics beyond request count/latency: retrieval and generation latency, cache hit ratio, abstentions, fallbacks, tokens.
- [ ] One JSON log line per request with `top_k`, chunk ids, scores, abstention flag.
- [~] LLM provider interface (`ollama`, `hosted`, `stub`) exists. Real generation not yet exercised end to end.

### 1.4 Indexing (spec section 3.1)
- [~] Extract (with OCR), clean, chunk, embed, store, with metadata `source, section, page, doc_version, superseded`. Code exists; **never run on the real corpus yet**.
- [ ] **Top gap:** the indexer Job runs `args: ["--dummy"]` and mounts **no corpus volume**, so the cluster cannot index the real documents. The Job and the CronJob need a corpus source (for example an init step that runs `corpus/fetch.py`, or a PVC/volume) and the real args.
- [ ] Three (size, overlap) configs measured on the golden set, in a table in `docs/PIPELINE.md`.

### 1.5 Kubernetes (spec section 4)
- [~] Manifests exist for namespace, api (3 replicas, probes, resources, rolling update), ui, chroma StatefulSet, redis, indexer Job and CronJob, ingress, configmap, serviceaccounts, networkpolicy, HPA.
- [ ] ConfigMap still says `RETRIEVER: stub`, `LLM_PROVIDER: stub`, `EMBED_MODEL: dummy-768`. It must say `chroma`, `ollama-host`, `nomic-embed-text` for a real run.
- [?] `kustomize build k8s/overlays/prod | kubeconform -strict -` passes.
- [?] Pods run on a Calico cluster; NetworkPolicy really blocks `ui` to `chroma`; DNS and Ollama-host egress allowed.
- [?] HPA shows a number, not `<unknown>`.
- [ ] Real `kubectl top pods` output committed to justify requests and limits.

### 1.6 Evaluation (spec section 5)
- [~] `eval/golden.yaml` has 15 questions. Its `relevant` sections were **not** checked against real chunks.
- [ ] `eval/results.json` committed (does not exist).
- [ ] `eval/baseline.json` must come from a real run. The current numbers have no run behind them.
- [ ] `docs/FAILURE-ANALYSIS.md`: four stages broken on purpose (untouched template).

### 1.7 Docs (spec sections 2, 3, 7, 8)
- [~] `docs/CORPUS.md`, ADR 0001-0004 exist. Re-read them against the final design.
- [ ] `README.md` (problem, CI badge, diagram, exact apply order, clean clone to answer, endpoint table, screenshot). Currently one paragraph.
- [ ] `docs/ENGINEERING-NOTES.md` (7 answers, with file and line references). Template only.
- [ ] `docs/PIPELINE.md` (real numbers). Template only.
- [ ] `docs/AI-USAGE.md` (honest disclosure). Template only.
- [ ] `docs/evidence/` replaced with real captures (the earlier files could not be traced to real events; do not submit them as they are).
- [ ] `python scripts/check_submission.py` prints no FAIL.

---

## 2. One-time setup (Windows)

`make` is **not installed** on this machine, so the Makefile targets below are given as plain commands. Use PowerShell unless a line says Git Bash.

Already installed in this session: `minikube`, `kubeconform`, `kustomize`, `kind`, `trivy`, `gh`, plus Docker Desktop and Ollama. Models: `nomic-embed-text` is pulled; `qwen2.5:3b` is there; the ConfigMap expects `llama3.2:3b`, so run `ollama pull llama3.2:3b` or change `LLM_MODEL` to `qwen2.5:3b`.

```powershell
# Python deps (once)
python -m venv .venv
.venv\Scripts\pip install pytest-cov==6.1.1 -r api/requirements-dev.txt -r indexer/requirements-dev.txt

# GitHub CLI login (once, browser): choose GitHub.com, HTTPS, log in as MannanJaffery
gh auth login
```

---

## 3. How to run it, in levels (stop at the first level that fails)

### Level 0: unit tests and lint (no Docker, no Ollama)
```powershell
cd api;     python -m pytest -q --cov=app --cov-report=term-missing --cov-fail-under=60
cd ..\indexer; python -m pytest -q
cd ..;      ruff check api indexer eval corpus
cd api;     mypy app; cd ..\indexer; mypy pipeline; cd ..
```
Works when: all tests pass, coverage >= 60% on `app`, ruff and mypy print no errors.
(Right now ruff and mypy report about 9 and 4 older errors; they are on the to-do list.)

### Level 1: API with stubs on your laptop
```powershell
cd api
$env:SERVE_UI_DIR="../ui"; $env:RETRIEVER="stub"; $env:LLM_PROVIDER="stub"
python -m uvicorn app.main:app --port 8000
```
Open http://localhost:8000 (chat UI). In another terminal:
```powershell
curl http://localhost:8000/healthz          # {"status":"alive"}
curl http://localhost:8000/readyz           # ready (stub)
curl -X POST http://localhost:8000/api/ask -H "Content-Type: application/json" -d '{"question":"What is the attendance requirement?"}'
curl http://localhost:8000/metrics          # Prometheus text
```
Works when: `/api/ask` returns JSON with `answer`, `citations`, `retrieved` (3 stub passages), and `X-Request-ID` is echoed.

### Level 2: embeddings and generation against your real Ollama
Ollama must listen on all interfaces so the cluster can reach it:
```powershell
# stop the Ollama tray app first, then:
$env:OLLAMA_HOST="0.0.0.0"; ollama serve
```
```powershell
curl http://localhost:11434/api/tags                                  # lists nomic-embed-text and your chat model
curl http://localhost:11434/api/embed -d '{"model":"nomic-embed-text","input":["hello"]}'
```
Works when: the embed call returns a 768-number vector.

### Level 3: the cluster
```powershell
minikube start --driver=docker --cni=calico --memory=6144 --cpus=4
minikube addons enable metrics-server
minikube addons enable ingress

docker build -t rahbar-api:dev api
docker build -t rahbar-indexer:dev indexer
docker build -t rahbar-ui:dev ui
minikube image load rahbar-api:dev
minikube image load rahbar-indexer:dev
minikube image load rahbar-ui:dev

kubectl apply -k k8s/overlays/dev
kubectl create secret generic rahbar-secret -n rahbar --from-literal=LLM_API_KEY=unused --dry-run=client -o yaml | kubectl apply -f -
kubectl get pods -n rahbar -w
```
Index (only meaningful once the top gap in 1.4 is fixed):
```powershell
kubectl create job --from=cronjob/reindex manual-reindex-1 -n rahbar
kubectl logs -n rahbar job/manual-reindex-1 -f
```
Reach it through the Ingress (docker driver on Windows needs a tunnel and a hosts entry):
```powershell
# terminal A (leave running, as Administrator if asked)
minikube tunnel
# add this line to C:\Windows\System32\drivers\etc\hosts (as Administrator):
#   127.0.0.1 rahbar.local
curl -X POST http://rahbar.local/api/ask -H "Content-Type: application/json" -d '{"question":"What CGPA puts a student on academic warning?"}'
```
Works when: all pods are `Running` and `READY` (api 3/3), the answer has citations that appear in `retrieved`, and an out-of-corpus question (for example "What are the hostel rules?") returns `answered_from_context: false`.

### Level 4: evaluation
```powershell
python eval/run_eval.py --api http://rahbar.local
# CI-style fixture run: python eval/run_eval.py --api http://rahbar.local --golden eval/fixtures/golden.fixture.yaml --out eval/results.fixture.json
```
Works when: exit code 0, `eval/results.json` written, abstention correctness is 1.0, citation validity >= 0.95, recall@5 within 5 points of `eval/baseline.json`.

### Level 5: CI and CD on GitHub
```powershell
gh run list --limit 10
gh run view <id> --log-failed
gh pr checks <pr-number>
```
Works when: every CI job is green on a PR to `main`, and `cd.yml` on `main` shows test, then build-push, then deploy all green, with images on Docker Hub tagged by commit SHA.

---

## 4. "Does it really work?" demonstrations the assignment asks you to show

| Claim | Command | You should see |
|---|---|---|
| Survives a deleted pod | `kubectl delete pod -n rahbar -l app.kubernetes.io/name=api --wait=false` then keep asking | answers keep coming; pod count returns to 3 |
| Scales and the Service follows | `kubectl scale deploy/api -n rahbar --replicas=4` then `kubectl get endpoints api -n rahbar` | 4 IPs listed |
| Rollout and undo | `kubectl set image deploy/api api=rahbar-api:<other> -n rahbar` ; `kubectl rollout status deploy/api -n rahbar` ; `kubectl rollout undo deploy/api -n rahbar` | no downtime; previous version serves again |
| Embedding guardrail | change `EMBED_MODEL` in the ConfigMap, `kubectl rollout restart deploy/api -n rahbar` | pods stay `0/1 READY`; `kubectl logs` names the conflict |
| Re-index without redeploy | `kubectl create job --from=cronjob/reindex manual-reindex-2 -n rahbar` | cache entries from before are no longer served |
| NetworkPolicy works | `kubectl exec -n rahbar deploy/ui -- wget -qO- -T2 http://chroma:8000/api/v2/heartbeat` | times out (ui must not reach chroma) |
| HPA reads CPU | `kubectl get hpa -n rahbar` | a percentage, never `<unknown>` |
| Resources justified | `kubectl top pods -n rahbar` | commit this output in `docs/evidence/` |
| Secrets not in Git | `git log -p --all -S"gsk_" --oneline` (and see 5.2) | nothing |

---

## 5. Checks you can run any time

### 5.1 Commits and authorship
```powershell
git rev-list --count --all                      # total commits (target 35-40+)
git shortlog -sne --all                         # commits per author
git log --format="%h %an <%ae> %s" origin/dev   # who wrote what
```
Each commit should be authored by whoever actually wrote it.

### 5.2 Secrets scan over full history
```powershell
trivy fs --scanners secret .
git log --all -p | Select-String -Pattern "api[_-]?key|secret|password|token|gsk_|sk-" | Select-Object -First 20
```
Must be clean, otherwise rotate the key and write the two-line incident note the assignment asks for.

### 5.3 Manifests and images
```powershell
kustomize build k8s/overlays/prod | kubeconform -strict -summary -
trivy image --severity HIGH,CRITICAL --ignore-unfixed rahbar-api:dev
```

### 5.4 The official lint of your submission
```powershell
python scripts/check_submission.py
```
No `FAIL` lines means the mechanical deductions are avoided. It is not a grade.

---

## 6. Final submission checklist (Google Classroom)

- [ ] Repository URL (public, or private with both instructors added)
- [ ] Link to a successful `cd.yml` run (test, then publish, then deploy)
- [ ] Docker Hub link showing SHA tags for api, ui, indexer
- [ ] `eval/results.json` and `eval/baseline.json` committed
- [ ] `docs/AI-USAGE.md` lists every AI tool used, what it wrote, and what you changed
- [ ] `python scripts/check_submission.py` clean
- [ ] Submitted before 23:59 PKT today; late submissions are not accepted

## 7. Automatic deductions to avoid (from the spec)

| Violation | Points | Status |
|---|---|---|
| Secret anywhere in Git history | -20 | scan with 5.2 |
| Real base64 Secret in a manifest | -15 | `secret.placeholder.yaml` only holds `REPLACE_ME` |
| Indexing at API startup | -10 | OK, indexer is a Job |
| Citation not matching a retrieved chunk | -10 | enforce and test |
| Must-abstain question answered | -10 | run the eval |
| Chroma/Redis without PVC, or NodePort/LoadBalancer | -8 | verify manifests |
| Embedding model not pinned or able to disagree silently | -8 | API fallback removed on the branch; indexer fallback and startup check still to do |
| Container without requests, or HPA `<unknown>` | -6 | verify live |
| Publish/deploy job without `needs:`, or `:latest` | -6 | CD rewrite pending |
| Manifests in `default` namespace | -5 | all use `rahbar` |
| README apply order not working from a clean clone | -5 | README pending |
| Direct commits to `main` | -4 | protect `main` |
