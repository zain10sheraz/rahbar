"""Stage 5: Store. The only code in the whole system that writes to Chroma."""

from __future__ import annotations

from typing import Any

from .config import IndexerSettings
from .models import Chunk, new_index_version


def get_client(settings: IndexerSettings) -> Any:
    import chromadb  # the thin client, from chromadb-client in requirements.txt
    from chromadb.config import Settings as ChromaSettings

    return chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                               settings=ChromaSettings(anonymized_telemetry=False))


def store(chunks: list[Chunk], vectors: list[list[float]], settings: IndexerSettings) -> int:
    """Write every chunk with its vector and metadata, and record the embedding model
    and vector dimension in the collection metadata (section 4.4). Return the count."""
    client = get_client(settings)
    dimension = len(vectors[0]) if vectors else 768

    # Recreate collection to guarantee consistent metadata and clear superseded items
    try:
        client.delete_collection(settings.collection)
    except Exception:
        pass

    collection = client.create_collection(
        name=settings.collection,
        metadata={
            "hnsw:space": "cosine",
            "embed_model": settings.embed_model,
            "dimension": dimension,
            "index_version": new_index_version(),
        },
    )

    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        chunk_batch = chunks[i : i + batch_size]
        vector_batch = vectors[i : i + batch_size]
        collection.add(
            ids=[c.id for c in chunk_batch],
            documents=[c.text for c in chunk_batch],
            embeddings=vector_batch,
            metadatas=[c.metadata() for c in chunk_batch],
        )

    return int(collection.count())
