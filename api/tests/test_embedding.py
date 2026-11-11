"""The embedding helper must fail loudly, never fall back to fake vectors."""

from __future__ import annotations

import httpx
import pytest

from app.config import Settings
from app.services import embedding
from app.services.embedding import EmbeddingError, embed_text, hash_vector


def test_dummy_model_is_deterministic_and_unit_length() -> None:
    a = hash_vector("same text")
    assert a == hash_vector("same text")
    assert a != hash_vector("other text")
    assert abs(sum(v * v for v in a) - 1.0) < 1e-6


def test_dummy_model_needs_no_network() -> None:
    settings = Settings(embed_model="dummy-768")
    assert len(embed_text(settings, "hello")) == 768


def test_real_model_calls_ollama_embed(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, object] = {}

    def fake_post(self: httpx.Client, url: str, json: dict) -> httpx.Response:
        seen["url"], seen["json"] = url, json
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", fake_post)
    vec = embed_text(Settings(embed_model="nomic-embed-text", ollama_url="http://o:1/"), "q")
    assert vec == [0.1, 0.2, 0.3]
    assert seen["url"] == "http://o:1/api/embed"
    assert seen["json"] == {"model": "nomic-embed-text", "input": ["q"]}


def test_backend_failure_raises_instead_of_faking_a_vector(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(self: httpx.Client, url: str, json: dict) -> httpx.Response:
        raise httpx.ConnectError("no route")

    monkeypatch.setattr(httpx.Client, "post", boom)
    with pytest.raises(EmbeddingError, match="nomic-embed-text"):
        embed_text(Settings(embed_model="nomic-embed-text"), "q")


def test_empty_vector_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    def empty(self: httpx.Client, url: str, json: dict) -> httpx.Response:
        return httpx.Response(200, json={"embeddings": [[]]}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.Client, "post", empty)
    with pytest.raises(EmbeddingError):
        embed_text(Settings(embed_model="nomic-embed-text"), "q")


def test_module_exposes_no_silent_fallback_name() -> None:
    assert not hasattr(embedding, "fallback_vector")
