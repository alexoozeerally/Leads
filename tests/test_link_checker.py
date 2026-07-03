"""Tests for the broken-link checker (mocked HTTP, no network)."""

from __future__ import annotations

import httpx
import pytest

from app.agents.link_checker import LinkChecker


@pytest.mark.asyncio
async def test_flags_4xx_and_connection_errors(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if "dead" in request.url.path:
            return httpx.Response(404)
        if "boom" in request.url.path:
            raise httpx.ConnectError("no route")
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs.pop("verify", None)
        return real_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr("app.agents.link_checker.httpx.AsyncClient", fake_client)

    checker = LinkChecker(user_agent="TestBot", max_links=10)
    result = await checker.check(
        ["https://x.example/ok", "https://x.example/dead", "https://x.example/boom"]
    )
    assert result.checked == 3
    assert set(result.broken) == {"https://x.example/dead", "https://x.example/boom"}
    assert result.broken_count == 2


@pytest.mark.asyncio
async def test_empty_links_returns_zero():
    checker = LinkChecker(user_agent="TestBot")
    result = await checker.check([])
    assert result.checked == 0 and result.broken == []


@pytest.mark.asyncio
async def test_respects_max_links(monkeypatch):
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200)

    transport = httpx.MockTransport(handler)
    real_client = httpx.AsyncClient

    def fake_client(*args, **kwargs):
        kwargs.pop("verify", None)
        return real_client(*args, transport=transport, **kwargs)

    monkeypatch.setattr("app.agents.link_checker.httpx.AsyncClient", fake_client)

    checker = LinkChecker(user_agent="TestBot", max_links=2)
    result = await checker.check([f"https://x.example/{i}" for i in range(10)])
    assert result.checked == 2
