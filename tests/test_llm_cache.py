"""Tests for the caching + rate-limiting LLM wrapper."""

from __future__ import annotations

import pytest

from app.agents.llm_cache import CachingRateLimitedClient
from app.agents.llm_client import ImageInput
from app.config.settings import Settings


class _CountingClient:
    def __init__(self) -> None:
        self.calls = 0

    async def complete_json(self, *, system, user, images=None) -> str:
        self.calls += 1
        return f'{{"n": {self.calls}}}'


def _settings(**kw) -> Settings:
    base = dict(llm_cache_enabled=True, anthropic_rate_limit_per_second=0)
    base.update(kw)
    return Settings(**base)


@pytest.mark.asyncio
async def test_identical_calls_are_cached():
    inner = _CountingClient()
    client = CachingRateLimitedClient(inner, _settings())
    a = await client.complete_json(system="s", user="u")
    b = await client.complete_json(system="s", user="u")
    assert a == b
    assert inner.calls == 1  # second call served from cache
    assert client.cache_hits == 1


@pytest.mark.asyncio
async def test_different_prompts_not_cached():
    inner = _CountingClient()
    client = CachingRateLimitedClient(inner, _settings())
    await client.complete_json(system="s", user="u1")
    await client.complete_json(system="s", user="u2")
    assert inner.calls == 2


@pytest.mark.asyncio
async def test_image_content_is_part_of_cache_key(tmp_path):
    img = tmp_path / "shot.png"
    img.write_bytes(b"AAAA")
    inner = _CountingClient()
    client = CachingRateLimitedClient(inner, _settings())

    await client.complete_json(system="s", user="u", images=[ImageInput(path=str(img))])
    await client.complete_json(system="s", user="u", images=[ImageInput(path=str(img))])
    assert inner.calls == 1  # unchanged screenshot -> cached (vision not re-run)

    img.write_bytes(b"BBBB")  # screenshot changed
    await client.complete_json(system="s", user="u", images=[ImageInput(path=str(img))])
    assert inner.calls == 2  # changed screenshot -> re-run


@pytest.mark.asyncio
async def test_cache_can_be_disabled():
    inner = _CountingClient()
    client = CachingRateLimitedClient(inner, _settings(llm_cache_enabled=False))
    await client.complete_json(system="s", user="u")
    await client.complete_json(system="s", user="u")
    assert inner.calls == 2
