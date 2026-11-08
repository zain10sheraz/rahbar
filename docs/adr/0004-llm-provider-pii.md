# ADR 0004: LLM Provider Selection and PII / Data Privacy Strategy

## Status
Accepted · 2026-11-08

## Context
Deploying LLMs for university academic and student assistance involves privacy considerations. Student questions may inadvertently contain personally identifiable information (PII) such as roll numbers, student names, phone numbers, or disciplinary matters.
Furthermore, evaluation and automated CI testing require deterministic, fast, offline execution without depending on external cloud API credits or rate limits.

## Decision
We implement a pluggable provider interface (`LLMProvider`) supporting multiple operational backends:
1. **Local Self-Hosted (Ollama):** For on-premise, privacy-sensitive environments where student queries never leave university infrastructure.
2. **Hosted Provider (Groq / OpenRouter / Google AI Studio):** For lightweight cloud setups where API keys are passed strictly through Kubernetes Secrets (`LLM_API_KEY`) and never logged or committed to source control.
3. **Deterministic Stub Provider (`StubProvider`):** For unit testing and offline CI execution without network requests or external dependencies.

Additionally:
- Request logging explicitly strips PII and only tracks request IDs, chunk IDs, and latency metrics.
- The model prompt is hardened against instruction injection, instructing the LLM to ignore meta-prompts inside document text and answer strictly from evidence passages.

## Options Considered
1. **Cloud-Only Proprietary APIs (OpenAI/Anthropic):** Rejected as the sole provider due to university data sovereignty policies and network costs.
2. **Local Model Hard-coded in Container:** Rejected because bundled LLM weights inflate container images to >5GB, making container pull and rollout unfeasible.
3. **Pluggable Interface with Local Ollama & Secret-Gated Hosted Fallback (Chosen):** Allows environment-specific runtime configuration via `LLM_PROVIDER` in `ConfigMap`.

## Consequences
- **Positive:** Zero vendor lock-in; seamless transition between local GPUs and cloud APIs.
- **Positive:** CI pipeline executes 100% offline using `StubProvider`.
- **Trade-off:** Local Ollama requires host machine memory resources when running outside cloud infrastructure.
