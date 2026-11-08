# api/app/services/cache.py
"""Simple Redis‑backed cache for vector‑search results.

Provides a minimal interface used by the semantic cache wrapper.
If ``CACHE_URL`` environment variable is defined and the ``redis`` package
is available, a real Redis client is used; otherwise an in‑memory dict is
used so the code runs locally without external services.
"""

import os
import json
import time
from typing import Any, Optional

try:
    import redis  # type: ignore
except ImportError:  # pragma: no cover
    redis = None


class Cache:
    def __init__(self) -> None:
        self.url = os.getenv("CACHE_URL")
        if self.url and redis:
            self.client = redis.from_url(self.url)
        else:
            self.client = None
            self._mem: dict[str, tuple[float, Any]] = {}

    def _now(self) -> float:
        return time.time()

    def get(self, key: str) -> Optional[Any]:
        if self.client:
            raw = self.client.get(key)
            return json.loads(raw) if raw else None
        entry = self._mem.get(key)
        if not entry:
            return None
        expire, value = entry
        if expire and expire < self._now():
            del self._mem[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        if self.client:
            payload = json.dumps(value)
            if ttl:
                self.client.setex(key, ttl, payload)
            else:
                self.client.set(key, payload)
        else:
            exp = self._now() + ttl if ttl else 0.0
            self._mem[key] = (exp, value)

    def delete(self, key: str) -> None:
        if self.client:
            self.client.delete(key)
        else:
            self._mem.pop(key, None)


def get_cache() -> Cache:
    """Singleton accessor used throughout the code base."""
    if not hasattr(get_cache, "_instance"):
        setattr(get_cache, "_instance", Cache())
    return getattr(get_cache, "_instance")
