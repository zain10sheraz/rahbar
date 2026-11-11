"""Ollama provider: ollama-host or ollama-incluster (section 3.5). Yours to build."""

from __future__ import annotations

from ...config import Settings
from ...schemas import Answer, Passage


import json
import logging
import httpx
from pydantic import ValidationError


log = logging.getLogger("rahbar.llm.ollama")

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


def _safe_fallback(question: str, reason: str = "Generation fallback triggered") -> Answer:
    return Answer(
        reasoning=reason,
        answer="I could not reliably generate an answer from the provided context.",
        citations=[],
        answered_from_context=False,
        confidence="low",
    )


class OllamaProvider:
    name = "ollama"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timeout = 120.0  # CPU inference of a 3B model is slow, especially on a cold start

    def generate(self, question: str, passages: list[Passage]) -> Answer:
        # If no passages passed relevance floor, immediately abstain
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

        # Up to 2 attempts: 1 initial call + 1 retry on validation/decoding error
        for attempt in range(2):
            try:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.post(
                        f"{self.settings.ollama_url.rstrip('/')}/api/chat",
                        json={
                            "model": self.settings.llm_model,
                            "messages": [
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": user_prompt},
                            ],
                            "format": "json",
                            "options": {
                                "temperature": self.settings.temperature,
                            },
                            "stream": False,
                        },
                    )
                    response.raise_for_status()
                    data = response.json()
                    content = data.get("message", {}).get("content", "{}")
                    parsed = json.loads(content)
                    return Answer.model_validate(parsed)
            except (json.JSONDecodeError, ValidationError) as err:
                log.warning("Validation error on attempt %d: %s. Retrying...", attempt + 1, err)
                continue
            except Exception as exc:
                log.error("Ollama request failed: %s", exc)
                break

        return _safe_fallback(question, "LLM failed validation after retry")
