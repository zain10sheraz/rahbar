"""Hosted free-tier provider (Groq, Google AI Studio, OpenRouter). Yours to build.

The key arrives as LLM_API_KEY from a Kubernetes Secret created on the command
line. It never appears in a file you commit, and never in a log line.
"""

from __future__ import annotations

from ...config import Settings
from ...schemas import Answer, Passage


import json
import logging
import httpx
from pydantic import ValidationError

from ...config import Settings
from ...schemas import Answer, Citation, Passage

log = logging.getLogger("rahbar.llm.hosted")

SYSTEM_PROMPT = """You are RAHBAR, an academic assistant for FAST-NUCES.
Answer the question ONLY based on the numbered passages below.
If the passages do not contain the answer, set answered_from_context to false and state clearly that the corpus does not cover this question.
You MUST output strictly in valid JSON matching this schema:
{
  "reasoning": "brief rationale",
  "answer": "clear, direct answer",
  "citations": [{"source": "filename.pdf", "section": "section title", "page": 1}],
  "answered_from_context": true or false,
  "confidence": "high" or "medium" or "low"
}
"""


def _safe_fallback(question: str, reason: str = "Hosted LLM fallback triggered") -> Answer:
    return Answer(
        reasoning=reason,
        answer="I could not reliably generate an answer from the provided context.",
        citations=[],
        answered_from_context=False,
        confidence="low",
    )


class HostedProvider:
    name = "hosted"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timeout = 30.0

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        if not passages:
            return Answer(
                reasoning="No relevant passages met the relevance threshold.",
                answer="The official university documents do not cover this question.",
                citations=[],
                answered_from_context=False,
                confidence="low",
            )

        evidence_text = "\n\n".join(
            f"[{i+1}] Source: {p.source}, Section: {p.section}, Page: {p.page or 1}\n{p.text}"
            for i, p in enumerate(passages)
        )
        user_prompt = f"Evidence:\n{evidence_text}\n\nQuestion: {question}"

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.settings.llm_api_key}",
        }

        # 1 call + 1 retry on validation failure
        for attempt in range(2):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        f"{self.settings.hosted_base_url.rstrip('/')}/chat/completions",
                        headers=headers,
                        json={
                            "model": self.settings.llm_model,
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": user_prompt},
                            ],
                            "response_format": {"type": "json_object"},
                            "temperature": self.settings.temperature,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = data["choices"][0]["message"]["content"]
                    parsed = json.loads(content)
                    return Answer.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as err:
                log.warning("Hosted LLM validation error on attempt %d: %s. Retrying...", attempt + 1, err)
                continue
            except Exception as exc:
                log.error("Hosted LLM API call failed: %s", exc)
                break

        return _safe_fallback(question, "Hosted LLM failed validation after retry")
