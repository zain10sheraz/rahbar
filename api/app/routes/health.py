"""Liveness and readiness (section 4.3). They answer different questions."""

from __future__ import annotations

from fastapi import APIRouter, Request, Response

router = APIRouter()


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """Is the process alive? Must never touch Chroma, Redis or the LLM."""
    return {"status": "alive"}


@router.get("/readyz")
def readyz(request: Request, response: Response) -> dict[str, object]:
    """Readiness probe. Checks Chroma reachability, non-empty collection, embedding model match,
    and Redis reachability. Returns 503 when any dependency or contract check fails."""
    settings = getattr(request.app.state, "settings", None)
    if not settings:
        return {"status": "ready", "checks": {}}

    # If running with stub retriever, stubs are immediately ready
    if settings.retriever == "stub":
        return {"status": "ready", "checks": {"retriever": "stub"}}

    checks: dict[str, object] = {}
    failed: list[str] = []

    # 1. Chroma reachability, collection existence, non-empty check, embedding-model mismatch check
    try:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        client = chromadb.HttpClient(
            host=settings.chroma_host,
            port=settings.chroma_port,
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection = client.get_collection(settings.collection)
        count = int(collection.count())
        checks["chroma_count"] = count
        if count <= 0:
            failed.append("chroma collection is empty")

        col_meta = collection.metadata or {}
        col_embed_model = col_meta.get("embed_model")
        checks["collection_embed_model"] = col_embed_model

        if col_embed_model and col_embed_model != settings.embed_model:
            failed.append(
                f"embedding model mismatch: collection has '{col_embed_model}', settings require '{settings.embed_model}'"
            )
        checks["chroma"] = "ok"
    except Exception as exc:
        failed.append(f"chroma error: {exc}")
        checks["chroma"] = "unreachable"

    # 2. Redis reachability
    try:
        import redis

        r = redis.Redis(host="redis", port=6379, socket_timeout=2.0)
        r.ping()
        checks["redis"] = "ok"
    except Exception as exc:
        failed.append(f"redis error: {exc}")
        checks["redis"] = "unreachable"

    if failed:
        response.status_code = 503
        return {"status": "not_ready", "failures": failed, "checks": checks}

    return {"status": "ready", "checks": checks}
