"""The real retriever. Yours to build (sections 3.2 and 4.4).

Connection details are already here; the query is not.
"""

from __future__ import annotations

from ..config import Settings
from ..schemas import Passage
from ..services.embedding import embed_text


class ChromaRetriever:
    name = "chroma"

    def __init__(self, settings: Settings) -> None:
        import chromadb  # the thin client, from chromadb-client in requirements.txt
        from chromadb.config import Settings as ChromaSettings

        self.settings = settings
        self.client = chromadb.HttpClient(host=settings.chroma_host, port=settings.chroma_port,
                                          settings=ChromaSettings(anonymized_telemetry=False))

    def _embed_query(self, question: str) -> list[float]:
        return embed_text(self.settings, question)

    def retrieve(self, question: str, k: int) -> list[Passage]:
        query_vector = self._embed_query(question)
        collection = self.client.get_collection(self.settings.collection)

        # Query top k, filtering out superseded policies
        results = collection.query(
            query_embeddings=[query_vector],
            n_results=k,
            where={"superseded": False},
        )

        passages: list[Passage] = []
        ids = results.get("ids", [[]])[0]
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0] if "distances" in results else [0.0] * len(ids)

        for chunk_id, doc_text, meta, dist in zip(ids, documents, metadatas, distances):
            # Chroma returns cosine distance; similarity = 1 - distance
            similarity = 1.0 - float(dist) if dist is not None else 0.5
            passages.append(
                Passage(
                    chunk_id=str(chunk_id),
                    text=str(doc_text),
                    source=str(meta.get("source", "unknown")),
                    section=str(meta.get("section", "unknown")),
                    page=int(meta["page"]) if meta.get("page") is not None else None,
                    score=round(similarity, 4),
                )
            )

        return passages
