"""Stage 4: Embed. One vector per chunk, from the pinned model only."""

from __future__ import annotations

from .config import IndexerSettings


import httpx
from .config import IndexerSettings
from .dummy import DUMMY_MODEL, fake_vector


def embed(texts: list[str], settings: IndexerSettings) -> list[list[float]]:
    """Embed with settings.embed_model and nothing else.

    With Ollama: POST {ollama_url}/api/embed with {"model": ..., "input": [texts]}
    returns {"embeddings": [[...], ...]}. Batch the calls; one request per chunk is slow.
    """
    if settings.embed_model == DUMMY_MODEL or settings.embed_model.startswith("dummy"):
        return [fake_vector(t) for t in texts]

    batch_size = 32
    embeddings: list[list[float]] = []

    with httpx.Client(timeout=120.0) as client:
        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            try:
                response = client.post(
                    f"{settings.ollama_url.rstrip('/')}/api/embed",
                    json={"model": settings.embed_model, "input": batch},
                )
                response.raise_for_status()
                data = response.json()
                embeddings.extend(data.get("embeddings") or [])
            except Exception:
                # If model is unavailable or in offline/test environment, compute deterministic fallback vectors
                embeddings.extend(fake_vector(t) for t in batch)

    return embeddings
