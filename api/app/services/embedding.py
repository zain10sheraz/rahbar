"""Question embedding with the pinned model (section 4.4).

One function used by both the retriever and the semantic cache, so they can never
embed with different models. There is deliberately NO silent fallback: if the
embedding backend fails, the request fails loudly. A hash-vector fallback would
return plausible-looking nonsense and no error anywhere.

Models whose name starts with "dummy" use a deterministic hash vector. That exists
only so the stub-based tests and the starter's dummy index run without a model.
"""

from __future__ import annotations

import hashlib
import math

import httpx

from ..config import Settings

DUMMY_DIM = 768


class EmbeddingError(RuntimeError):
    """The embedding backend was unreachable or returned something unusable."""


def hash_vector(text: str, dim: int = DUMMY_DIM) -> list[float]:
    """Deterministic unit vector derived from the text. Test and dummy-index use only."""
    values: list[float] = []
    seed = text.encode()
    while len(values) < dim:
        seed = hashlib.sha256(seed).digest()
        values.extend((b - 127.5) / 127.5 for b in seed)
    values = values[:dim]
    norm = math.sqrt(sum(v * v for v in values)) or 1.0
    return [v / norm for v in values]


def embed_text(settings: Settings, text: str) -> list[float]:
    """Embed one string with settings.embed_model. Raise EmbeddingError on any failure."""
    if settings.embed_model.startswith("dummy"):
        return hash_vector(text)
    try:
        with httpx.Client(timeout=15.0) as client:
            res = client.post(
                f"{settings.ollama_url.rstrip('/')}/api/embed",
                json={"model": settings.embed_model, "input": [text]},
            )
            res.raise_for_status()
            vector = res.json()["embeddings"][0]
    except Exception as exc:
        raise EmbeddingError(
            f"embedding with {settings.embed_model!r} via {settings.ollama_url} failed: {exc}"
        ) from exc
    if not vector:
        raise EmbeddingError(f"model {settings.embed_model!r} returned an empty vector")
    return [float(v) for v in vector]
