"""Semantic cache (section 3.3).

A lookup embeds the question with the pinned model and compares it by cosine
similarity against the questions already answered. A hit is a similarity at or
above CACHE_THRESHOLD (read from the ConfigMap). Storage is Redis; with no
REDIS_HOST the cache lives in process memory so tests and `make dev` need nothing.

Never cached (a cached mistake is served to everyone):
  * follow-up questions, which only make sense with the previous turn
  * abstentions and out-of-scope answers (answered_from_context is false)
  * low-confidence answers and the canned fallback after a validation failure

Entries carry the index version they were answered under. When the indexer Job
rebuilds the index it stamps a new version into the Chroma collection metadata,
and entries from an older version are ignored and removed. Re-indexing therefore
expires the cache without the indexer ever needing network access to Redis.
"""

from __future__ import annotations

import json
import logging
import math
import re
import time
import uuid
from collections.abc import Callable
from functools import lru_cache
from typing import Any, Protocol

from ..config import Settings
from ..schemas import AskResponse
from .embedding import embed_text, hash_vector

log = logging.getLogger("rahbar.cache")

MAX_ENTRIES = 200

# Words that only make sense relative to an earlier turn.
_FOLLOW_UP = re.compile(
    r"^\s*(and|also|then|so|but|what about|how about)\b"
    r"|\b(that|those|them|it|its|this one|the same|previous|above|earlier|former|latter)\b",
    re.IGNORECASE,
)


def cosine(a: list[float], b: list[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


class CacheBackend(Protocol):
    def entries(self) -> list[dict[str, Any]]: ...
    def put(self, entry: dict[str, Any], ttl: int) -> None: ...
    def drop(self, ids: list[str]) -> None: ...


class MemoryBackend:
    def __init__(self) -> None:
        self._data: dict[str, tuple[float, dict[str, Any]]] = {}

    def entries(self) -> list[dict[str, Any]]:
        now = time.time()
        self._data = {k: v for k, v in self._data.items() if v[0] > now}
        return [dict(e, id=k) for k, (_, e) in self._data.items()]

    def put(self, entry: dict[str, Any], ttl: int) -> None:
        self._data[uuid.uuid4().hex] = (time.time() + ttl, entry)
        while len(self._data) > MAX_ENTRIES:
            self._data.pop(next(iter(self._data)))

    def drop(self, ids: list[str]) -> None:
        for i in ids:
            self._data.pop(i, None)


class RedisBackend:
    """Entries are JSON strings under rahbar:cache:<id>; a sorted set orders them by age."""

    INDEX = "rahbar:cache:index"

    def __init__(self, host: str, port: int) -> None:
        import redis

        # Any: redis-py types sync and async clients as one union that mypy cannot narrow.
        self.client: Any = redis.Redis(host=host, port=port, socket_timeout=2.0,
                                       decode_responses=True)

    def entries(self) -> list[dict[str, Any]]:
        ids = list(self.client.zrange(self.INDEX, 0, -1))
        if not ids:
            return []
        raws = self.client.mget([f"rahbar:cache:{i}" for i in ids])
        out: list[dict[str, Any]] = []
        gone: list[str] = []
        for i, raw in zip(ids, raws):
            if raw is None:
                gone.append(i)  # expired by its TTL
            else:
                out.append(dict(json.loads(raw), id=i))
        if gone:
            self.client.zrem(self.INDEX, *gone)
        return out

    def put(self, entry: dict[str, Any], ttl: int) -> None:
        entry_id = uuid.uuid4().hex
        pipe = self.client.pipeline()
        pipe.setex(f"rahbar:cache:{entry_id}", ttl, json.dumps(entry))
        pipe.zadd(self.INDEX, {entry_id: time.time()})
        pipe.zcard(self.INDEX)
        size = int(pipe.execute()[-1])
        if size > MAX_ENTRIES:
            oldest = self.client.zrange(self.INDEX, 0, size - MAX_ENTRIES - 1)
            self.drop([str(i) for i in oldest])

    def drop(self, ids: list[str]) -> None:
        if ids:
            self.client.delete(*[f"rahbar:cache:{i}" for i in ids])
            self.client.zrem(self.INDEX, *ids)


class SemanticCache:
    def __init__(
        self,
        settings: Settings,
        *,
        embedder: Callable[[str], list[float]] | None = None,
        backend: CacheBackend | None = None,
        version_provider: Callable[[], str] | None = None,
    ) -> None:
        self.threshold = settings.cache_threshold
        self.ttl = settings.cache_ttl
        self._embed = embedder or (lambda text: embed_text(settings, text))
        if backend is not None:
            self._backend: CacheBackend = backend
        elif settings.redis_host:
            self._backend = RedisBackend(settings.redis_host, settings.redis_port)
        else:
            self._backend = MemoryBackend()
        self._version = version_provider or (lambda: "")

    # -- rules ---------------------------------------------------------------
    def is_never_cache(self, question: str, response: AskResponse | None = None) -> bool:
        """True when this question, or this answer to it, must not be cached or served."""
        if _FOLLOW_UP.search(question):
            return True
        if response is not None and (
            not response.answered_from_context or response.confidence == "low"
        ):
            return True
        return False

    # -- operations ----------------------------------------------------------
    def lookup(self, question: str) -> tuple[AskResponse, float] | None:
        """Return (cached response, similarity) on a hit, else None. Never raises."""
        if self.is_never_cache(question):
            return None
        try:
            vector = self._embed(question)
            version = self._version()
            stale: list[str] = []
            best: tuple[float, dict[str, Any]] | None = None
            for entry in self._backend.entries():
                if entry.get("version") != version:
                    stale.append(entry["id"])
                    continue
                sim = cosine(vector, entry["vec"])
                if best is None or sim > best[0]:
                    best = (sim, entry)
            if stale:
                self._backend.drop(stale)
        except Exception as exc:  # the cache is an optimisation: a failure is a miss
            log.warning("cache lookup failed", extra={"error": str(exc)})
            return None
        if best is not None and best[0] >= self.threshold:
            return AskResponse.model_validate(best[1]["response"]), best[0]
        return None

    def store(self, question: str, response: AskResponse) -> bool:
        """Cache the answer unless a never-cache rule applies. Return True when stored."""
        if self.is_never_cache(question, response):
            return False
        try:
            entry = {
                "q": question,
                "vec": self._embed(question),
                "version": self._version(),
                "response": response.model_dump(mode="json"),
            }
            self._backend.put(entry, self.ttl)
        except Exception as exc:
            log.warning("cache store failed", extra={"error": str(exc)})
            return False
        return True


@lru_cache(maxsize=1)
def get_semantic_cache(settings: Settings) -> SemanticCache:
    """Process-wide cache. The stub retriever uses hash vectors so tests need no model."""
    if settings.retriever == "stub":
        return SemanticCache(settings, embedder=hash_vector)
    return SemanticCache(settings)
