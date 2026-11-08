"""Semantic cache behaviour (section 3.3): threshold, never-cache rules, invalidation."""

from __future__ import annotations

import time

import pytest

from app.config import Settings
from app.schemas import AskResponse
from app.services.cache import MemoryBackend, SemanticCache, cosine

# Hand-made 3-d "embeddings": same topic = near-parallel vectors, other topic = orthogonal.
VECTORS = {
    "What CGPA puts a student on academic warning?": [1.0, 0.0, 0.0],
    "Which CGPA means academic warning for students?": [0.97, 0.24, 0.0],  # cos ~0.971
    "What is the fee per credit hour?": [0.0, 1.0, 0.0],
    "What is the refund policy?": [0.0, 0.0, 1.0],
}


def embed(text: str) -> list[float]:
    return VECTORS[text]


def response(*, answered: bool = True, confidence: str = "high") -> AskResponse:
    return AskResponse(
        request_id="r1", answer="2.00", citations=[], answered_from_context=answered,
        confidence=confidence, retrieved=[], provider="stub",  # type: ignore[arg-type]
    )


def make(threshold: float = 0.95, version: str = "v1", ttl: int = 300) -> tuple[SemanticCache, list[str]]:
    holder = [version]
    cache = SemanticCache(
        Settings(cache_threshold=threshold, cache_ttl=ttl),
        embedder=embed, backend=MemoryBackend(), version_provider=lambda: holder[0],
    )
    return cache, holder


def test_cosine_basics() -> None:
    assert cosine([1, 0], [1, 0]) == pytest.approx(1.0)
    assert cosine([1, 0], [0, 1]) == pytest.approx(0.0)
    assert cosine([1, 0], [1, 0, 0]) == 0.0


def test_paraphrase_hits_at_or_above_threshold() -> None:
    cache, _ = make(threshold=0.95)
    assert cache.store("What CGPA puts a student on academic warning?", response())
    hit = cache.lookup("Which CGPA means academic warning for students?")
    assert hit is not None and hit[1] >= 0.95


def test_threshold_decides_the_hit() -> None:
    cache, _ = make(threshold=0.99)
    cache.store("What CGPA puts a student on academic warning?", response())
    assert cache.lookup("Which CGPA means academic warning for students?") is None


def test_different_topic_never_hits() -> None:
    cache, _ = make(threshold=0.5)
    cache.store("What CGPA puts a student on academic warning?", response())
    assert cache.lookup("What is the fee per credit hour?") is None


@pytest.mark.parametrize("question", ["what about that?", "And the fee?", "Is it allowed?",
                                      "How about the previous semester?"])
def test_follow_ups_are_never_cached_or_served(question: str) -> None:
    cache, _ = make()
    assert cache.is_never_cache(question) is True
    assert cache.store(question, response()) is False
    assert cache.lookup(question) is None


def test_standalone_questions_are_cacheable() -> None:
    cache, _ = make()
    assert cache.is_never_cache("What is the refund policy?") is False


def test_abstentions_and_low_confidence_are_never_stored() -> None:
    cache, _ = make()
    q = "What is the refund policy?"
    assert cache.store(q, response(answered=False, confidence="low")) is False
    assert cache.store(q, response(confidence="low")) is False
    assert cache.lookup(q) is None


def test_reindex_expires_the_cache() -> None:
    cache, version = make()
    q = "What is the fee per credit hour?"
    cache.store(q, response())
    assert cache.lookup(q) is not None
    version[0] = "v2"  # the indexer Job stamped a new index_version
    assert cache.lookup(q) is None
    version[0] = "v1"  # and the stale entry was removed, not merely hidden
    assert cache.lookup(q) is None


def test_entries_expire_after_ttl() -> None:
    cache, _ = make(ttl=1)
    q = "What is the fee per credit hour?"
    cache.store(q, response())
    assert cache.lookup(q) is not None
    time.sleep(1.1)
    assert cache.lookup(q) is None


def test_embedding_failure_is_a_miss_not_an_error() -> None:
    def boom(_: str) -> list[float]:
        raise RuntimeError("ollama down")

    cache = SemanticCache(Settings(), embedder=boom, backend=MemoryBackend())
    assert cache.lookup("What is the fee per credit hour?") is None
    assert cache.store("What is the fee per credit hour?", response()) is False


def test_api_serves_a_repeat_question_from_cache_with_its_own_request_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi.testclient import TestClient

    monkeypatch.setenv("RETRIEVER", "stub")
    monkeypatch.setenv("LLM_PROVIDER", "stub")
    from app.main import app

    calls = {"n": 0}
    with TestClient(app) as client:
        from app.schemas import Answer

        def counting(question: str, passages: list) -> Answer:  # type: ignore[type-arg]
            calls["n"] += 1
            return Answer(reasoning="r", answer="2.00", citations=[],
                          answered_from_context=True, confidence="high")

        monkeypatch.setattr(app.state.provider, "generate", counting)
        q = {"question": "What does the stub say about caching?"}
        first = client.post("/api/ask", json=q, headers={"X-Request-ID": "one"}).json()
        second = client.post("/api/ask", json=q, headers={"X-Request-ID": "two"}).json()
    assert calls["n"] == 1  # the second answer never reached the model
    assert first["request_id"] == "one" and second["request_id"] == "two"
    assert first["answer"] == second["answer"]
