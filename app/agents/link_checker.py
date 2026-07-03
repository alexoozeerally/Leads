"""Bounded, polite broken-link checking.

Checks a capped sample of a page's links with HEAD requests. Injectable so tests
run offline. When checking is skipped or fails, the caller reports "not checked"
rather than inventing a result.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

from app.config.logging import get_logger

log = get_logger(__name__)


@dataclass
class LinkCheckResult:
    checked: int
    broken: list[str]

    @property
    def broken_count(self) -> int:
        return len(self.broken)


class LinkChecker:
    """Checks up to ``max_links`` links for a 4xx/5xx or connection failure."""

    def __init__(
        self,
        *,
        user_agent: str,
        max_links: int = 15,
        timeout: float = 8.0,
        concurrency: int = 5,
        verify_tls: bool = True,
    ) -> None:
        self._ua = user_agent
        self._max_links = max_links
        self._timeout = timeout
        self._verify_tls = verify_tls
        self._sem = asyncio.Semaphore(concurrency)

    async def _check_one(self, client: httpx.AsyncClient, url: str) -> str | None:
        async with self._sem:
            try:
                resp = await client.head(url, follow_redirects=True)
                if resp.status_code >= 400:
                    # Some servers reject HEAD; confirm with a light GET.
                    resp = await client.get(url, follow_redirects=True)
                return url if resp.status_code >= 400 else None
            except httpx.HTTPError:
                return url

    async def check(self, links: list[str]) -> LinkCheckResult:
        sample = links[: self._max_links]
        if not sample:
            return LinkCheckResult(checked=0, broken=[])
        async with httpx.AsyncClient(
            timeout=self._timeout, headers={"User-Agent": self._ua}, verify=self._verify_tls
        ) as client:
            outcomes = await asyncio.gather(*(self._check_one(client, u) for u in sample))
        broken = [u for u in outcomes if u]
        return LinkCheckResult(checked=len(sample), broken=broken)
