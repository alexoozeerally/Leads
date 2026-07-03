"""Crawler politeness: robots.txt checking and per-host rate limiting.

These are compliance-critical. The crawler must respect robots.txt, identify
itself truthfully, and never exceed the configured per-host request rate.
"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from app.config.logging import get_logger

log = get_logger(__name__)


class RateLimiter:
    """Simple async per-host rate limiter (min interval between requests)."""

    def __init__(self, per_host_per_second: float) -> None:
        self._min_interval = 1.0 / per_host_per_second if per_host_per_second > 0 else 0.0
        self._last: dict[str, float] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, host: str) -> asyncio.Lock:
        if host not in self._locks:
            self._locks[host] = asyncio.Lock()
        return self._locks[host]

    async def acquire(self, host: str) -> None:
        if self._min_interval <= 0:
            return
        async with self._lock_for(host):
            now = time.monotonic()
            last = self._last.get(host, 0.0)
            wait = self._min_interval - (now - last)
            if wait > 0:
                await asyncio.sleep(wait)
            self._last[host] = time.monotonic()


class RobotsCache:
    """Fetches and caches robots.txt rules per host."""

    def __init__(self, user_agent: str, *, respect: bool = True) -> None:
        self._user_agent = user_agent
        self._respect = respect
        self._cache: dict[str, RobotFileParser | None] = {}

    async def _load(self, base: str) -> RobotFileParser | None:
        robots_url = f"{base}/robots.txt"
        try:
            async with httpx.AsyncClient(
                timeout=10, headers={"User-Agent": self._user_agent}, follow_redirects=True
            ) as client:
                resp = await client.get(robots_url)
            parser = RobotFileParser()
            if resp.status_code >= 400:
                parser.parse([])  # no robots.txt -> allow all
            else:
                parser.parse(resp.text.splitlines())
            return parser
        except httpx.HTTPError as exc:
            log.warning("robots.fetch_failed", url=robots_url, error=str(exc))
            return None  # unknown -> be cautious upstream

    async def allowed(self, url: str) -> bool:
        """Return whether ``url`` may be fetched for our user agent."""
        if not self._respect:
            return True
        parsed = urlparse(url)
        base = f"{parsed.scheme}://{parsed.netloc}"
        if base not in self._cache:
            self._cache[base] = await self._load(base)
        parser = self._cache[base]
        if parser is None:
            # Couldn't read robots.txt: default to allowed but log it.
            return True
        return parser.can_fetch(self._user_agent, url)
