"""Tests for crawler politeness: rate limiting and robots.txt."""

from __future__ import annotations

import httpx
import pytest

from app.crawler.politeness import RateLimiter, RobotsCache


@pytest.mark.asyncio
async def test_rate_limiter_enforces_min_interval(monkeypatch):
    limiter = RateLimiter(per_host_per_second=1000)  # 1ms interval
    sleeps: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("app.crawler.politeness.asyncio.sleep", fake_sleep)
    await limiter.acquire("host")  # first call, no wait
    await limiter.acquire("host")  # second call, should wait
    assert any(s > 0 for s in sleeps)


@pytest.mark.asyncio
async def test_rate_limiter_disabled_when_zero(monkeypatch):
    limiter = RateLimiter(per_host_per_second=0)
    called = False

    async def fake_sleep(seconds: float) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr("app.crawler.politeness.asyncio.sleep", fake_sleep)
    await limiter.acquire("host")
    await limiter.acquire("host")
    assert called is False


def _robots_client(body: str, status: int = 200) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_robots_disallows(monkeypatch):
    cache = RobotsCache("LeadFinderBot", respect=True)

    async def fake_load(base: str):
        from urllib.robotparser import RobotFileParser

        p = RobotFileParser()
        p.parse(["User-agent: *", "Disallow: /"])
        return p

    monkeypatch.setattr(cache, "_load", fake_load)
    assert await cache.allowed("https://x.example/page") is False


@pytest.mark.asyncio
async def test_robots_allows_when_not_respected():
    cache = RobotsCache("LeadFinderBot", respect=False)
    assert await cache.allowed("https://x.example/anything") is True
