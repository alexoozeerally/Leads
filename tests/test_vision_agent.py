"""Tests for the Vision agent using the deterministic mock LLM client."""

from __future__ import annotations

import pytest

from app.agents.llm_client import MockLLMClient
from app.agents.vision import VISION_DIMENSIONS, VisionAgent
from app.schemas.audit import WebsiteState
from app.schemas.business import Business
from app.schemas.context import AuditContext, CrawlResult


def _ctx(state: WebsiteState, desktop: str | None) -> AuditContext:
    crawl = CrawlResult(url="https://x.example", state=state, desktop_screenshot=desktop)
    return AuditContext(business=Business(name="Test Co", source_provider="csv"), crawl=crawl)


@pytest.mark.asyncio
async def test_vision_scores_all_dimensions_with_explanations(tmp_path):
    shot = tmp_path / "d.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header; mock ignores content
    agent = VisionAgent(client=MockLLMClient())
    result = await agent.run(_ctx(WebsiteState.OK, str(shot)))
    for dim in VISION_DIMENSIONS:
        assert dim in result.scores
        assert result.scores[dim].explanation  # every score explains itself
        assert 0 <= result.scores[dim].value <= 10
    assert "first_impression" in result.scores


@pytest.mark.asyncio
async def test_vision_no_site_is_max_opportunity_and_honest():
    agent = VisionAgent(client=MockLLMClient())
    result = await agent.run(_ctx(WebsiteState.NO_SITE, None))
    assert all(s.value == 0 for s in result.scores.values())
    assert "no website" in result.notes.lower()
    # It must not fabricate a design assessment when there's nothing to see.
    assert result.raw.get("state") == WebsiteState.NO_SITE.value


@pytest.mark.asyncio
async def test_vision_uses_canned_response_when_registered(tmp_path):
    shot = tmp_path / "d.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")
    canned = {
        "first_impression": 8,
        "estimated_site_age_years": 1,
        "dimensions": {
            dim: {"score": 8, "explanation": f"{dim} looks great"} for dim in VISION_DIMENSIONS
        },
        "summary": "A strong, modern site.",
    }
    client = MockLLMClient(responses={"web-design director": canned})
    agent = VisionAgent(client=client)
    result = await agent.run(_ctx(WebsiteState.OK, str(shot)))
    assert result.scores["modernity"].value == 8
    assert result.notes == "A strong, modern site."
    assert client.calls  # the mock actually received the call
