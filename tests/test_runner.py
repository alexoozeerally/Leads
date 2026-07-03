"""Tests for the structured-output runner: JSON extraction, retries, hard fail."""

from __future__ import annotations

import pytest
from pydantic import BaseModel

from app.agents.runner import generate_structured
from app.exceptions import AgentOutputError


class _Schema(BaseModel):
    value: int
    label: str


class _ScriptedClient:
    """Returns a preset sequence of responses, one per call."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.calls = 0

    async def complete_json(self, *, system, user, images=None) -> str:
        resp = self._responses[min(self.calls, len(self._responses) - 1)]
        self.calls += 1
        return resp


@pytest.mark.asyncio
async def test_parses_clean_json():
    client = _ScriptedClient(['{"value": 3, "label": "ok"}'])
    result = await generate_structured(client, system="s", user="u", schema=_Schema)
    assert result.value == 3 and result.label == "ok"


@pytest.mark.asyncio
async def test_strips_code_fences_and_prose():
    client = _ScriptedClient(['Here you go:\n```json\n{"value": 1, "label": "x"}\n```'])
    result = await generate_structured(client, system="s", user="u", schema=_Schema)
    assert result.value == 1


@pytest.mark.asyncio
async def test_retries_then_succeeds():
    client = _ScriptedClient(["not json at all", '{"value": 9, "label": "late"}'])
    result = await generate_structured(client, system="s", user="u", schema=_Schema, max_retries=2)
    assert result.value == 9
    assert client.calls == 2  # first failed, second succeeded


@pytest.mark.asyncio
async def test_fails_loudly_after_retries():
    client = _ScriptedClient(["garbage"])
    with pytest.raises(AgentOutputError):
        await generate_structured(client, system="s", user="u", schema=_Schema, max_retries=1)
    assert client.calls == 2  # initial + 1 retry
