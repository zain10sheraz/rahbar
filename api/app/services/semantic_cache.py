# api/app/services/semantic_cache.py
"""High‑level semantic cache used by the answer service.

It stores the full AskResponse object keyed by the raw question string.
The underlying storage is provided by api.app.services.cache which
uses Redis when CACHE_URL is defined, otherwise falls back to an
in‑memory store. A modest TTL (default 300 seconds) is applied so that
stale answers expire automatically.
"""

import json
from typing import Optional

from .cache import get_cache
from ..schemas import AskResponse

DEFAULT_TTL = 300  # seconds – keep cached answers for 5 min by default


class SemanticCache:
    def __init__(self, ttl: int = DEFAULT_TTL) -> None:
        self.ttl = ttl
        self._backend = get_cache()

    def _key(self, question: str) -> str:
        return f"semantic_cache:{question}"

    def lookup(self, question: str) -> Optional[AskResponse]:
        raw = self._backend.get(self._key(question))
        if raw is None:
            return None
        data = json.loads(raw)
        return AskResponse(**data)

    def store(self, question: str, response: AskResponse) -> None:
        payload = json.dumps(response.dict())
        self._backend.set(self._key(question), payload, ttl=self.ttl)


def get_semantic_cache(settings: any) -> SemanticCache:
    ttl = getattr(settings, "cache_ttl", DEFAULT_TTL)
    return SemanticCache(ttl=ttl)
