# api/app/services/semantic_cache.py
"""High-level answer cache used by the answer service.

It stores the full AskResponse keyed by the normalised question string. The
underlying storage is provided by app.services.cache, which uses Redis when
CACHE_URL is defined and an in-memory store otherwise. A TTL (default 300 s)
makes cached answers expire on their own.

Never-cache rules: abstentions/fallbacks (answered_from_context is false) and
context-dependent follow-ups ("what about that?") are never stored, so a
transient failure or a vague question cannot be replayed to the next caller.
"""

import json
import re
from typing import Any, Optional

from ..schemas import AskResponse
from .cache import get_cache

DEFAULT_TTL = 300  # seconds

_FOLLOW_UP = re.compile(
    r"^(and |but |what about|how about|why|so |then )|\b(that|this|it|those|these|they|them|the same|above|previous)\b",
    re.IGNORECASE,
)


class SemanticCache:
    def __init__(self, settings: Any = None, ttl: Optional[int] = None) -> None:
        self.ttl = ttl if ttl is not None else getattr(settings, "cache_ttl", DEFAULT_TTL)
        self._backend = get_cache()

    def _key(self, question: str) -> str:
        return f"semantic_cache:{' '.join(question.lower().split())}"

    def is_never_cache(self, question: str, response: Optional[AskResponse] = None) -> bool:
        if _FOLLOW_UP.search(question.strip()):
            return True
        if response is not None and not response.answered_from_context:
            return True
        return False

    def lookup(self, question: str) -> Optional[AskResponse]:
        if self.is_never_cache(question):
            return None
        raw = self._backend.get(self._key(question))
        if raw is None:
            return None
        data = json.loads(raw) if isinstance(raw, str) else raw
        return AskResponse(**data)

    def store(self, question: str, response: AskResponse) -> None:
        if self.is_never_cache(question, response):
            return
        self._backend.set(self._key(question), json.dumps(response.model_dump(mode="json")), ttl=self.ttl)


def get_semantic_cache(settings: Any) -> SemanticCache:
    return SemanticCache(settings)
