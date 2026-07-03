"""Caching + per-API rate-limiting wrapper for any :class:`LLMClient`.

- **Cache**: identical calls (same system + user + image bytes) return the cached
  response, so vision is never re-run on unchanged screenshots — the key includes
  a hash of each image's content.
- **Rate limit**: caps requests per second against the API, complementing the
  crawler's per-host limiter.

Both are transparent: the wrapper implements the same ``complete_json`` contract,
so agents are unaware they're wrapped.
"""

from __future__ import annotations

import asyncio
import hashlib
import time
from pathlib import Path

from app.agents.llm_client import ImageInput, LLMClient
from app.config.logging import get_logger
from app.config.settings import Settings, get_settings

log = get_logger(__name__)


class _ApiRateLimiter:
    def __init__(self, per_second: float) -> None:
        self._min_interval = 1.0 / per_second if per_second > 0 else 0.0
        self._last = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last = time.monotonic()


class CachingRateLimitedClient:
    """Wraps an LLMClient with an in-memory cache and an API rate limiter."""

    def __init__(self, inner: LLMClient, settings: Settings | None = None) -> None:
        self._inner = inner
        settings = settings or get_settings()
        self._cache_enabled = settings.llm_cache_enabled
        self._cache: dict[str, str] = {}
        self._limiter = _ApiRateLimiter(settings.anthropic_rate_limit_per_second)
        self.cache_hits = 0
        self.cache_misses = 0

    @staticmethod
    def _key(system: str, user: str, images: list[ImageInput] | None) -> str:
        h = hashlib.sha256()
        h.update(system.encode())
        h.update(b"\0")
        h.update(user.encode())
        for img in images or []:
            h.update(b"\0img\0")
            try:
                h.update(hashlib.sha256(Path(img.path).read_bytes()).digest())
            except OSError:
                h.update(img.path.encode())
        return h.hexdigest()

    async def complete_json(
        self, *, system: str, user: str, images: list[ImageInput] | None = None
    ) -> str:
        key = self._key(system, user, images) if self._cache_enabled else None
        if key is not None and key in self._cache:
            self.cache_hits += 1
            log.info("llm.cache_hit")
            return self._cache[key]

        self.cache_misses += 1
        await self._limiter.acquire()
        result = await self._inner.complete_json(system=system, user=user, images=images)
        if key is not None:
            self._cache[key] = result
        return result
