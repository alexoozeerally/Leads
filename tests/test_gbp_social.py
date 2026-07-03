"""Tests for GBP and social analysers — data-available-only, no fabrication."""

from __future__ import annotations

import pytest

from app.agents.gbp import GBPAgent
from app.agents.social import SocialAgent
from app.schemas.business import Business
from app.schemas.context import AuditContext, CrawlResult


def _ctx(biz: Business, links: list[str] | None = None) -> AuditContext:
    crawl = CrawlResult(url="https://x.example/", links=links or []) if links is not None else None
    return AuditContext(business=biz, crawl=crawl)


@pytest.mark.asyncio
async def test_gbp_scores_present_fields_and_marks_unknown():
    biz = Business(
        name="Clifton Dental",
        source_provider="csv",
        category="Dentist",
        address="88 Whiteladies Rd",
        phone="0117 900 0003",
        website="https://clifton.example",
        rating=4.3,
        review_count=215,
        # opening_hours intentionally omitted -> must be reported unknown
    )
    result = await GBPAgent().run(_ctx(biz))
    assert "reviews" in result.scores
    assert "nap_consistency" in result.scores
    assert result.scores["nap_consistency"].value == 10  # name+address+phone
    assert "opening_hours" in result.raw["unknown"]
    assert result.raw["available"] is True


@pytest.mark.asyncio
async def test_gbp_reports_unknown_when_no_data():
    biz = Business(name="Mystery Co", source_provider="osm")  # only a name
    result = await GBPAgent().run(_ctx(biz))
    # Name alone still yields a NAP score, but reviews/hours/category are unknown.
    assert "reviews/rating" in result.raw["unknown"]
    assert "opening_hours" in result.raw["unknown"]
    assert "category" in result.raw["unknown"]


@pytest.mark.asyncio
async def test_gbp_no_business_data_at_all_is_unavailable():
    # A business with only a name and nothing else GBP-like beyond NAP-name.
    biz = Business(name="X", source_provider="osm")
    result = await GBPAgent().run(_ctx(biz))
    # nap_consistency (name) is the only score; reviews/hours/category unknown.
    assert set(result.scores) <= {"nap_consistency"}


@pytest.mark.asyncio
async def test_social_detects_from_provider_and_crawl():
    biz = Business(
        name="Co",
        source_provider="csv",
        social_links={"facebook": "https://facebook.com/co"},
    )
    result = await SocialAgent().run(
        _ctx(biz, links=["https://instagram.com/co", "https://x.co/p"])
    )
    assert set(result.raw["present"]) >= {"facebook", "instagram"}
    assert "linkedin" in result.raw["unknown"]
    assert result.scores["presence"].value > 0


@pytest.mark.asyncio
async def test_social_reports_unknown_when_none():
    biz = Business(name="Co", source_provider="osm")
    result = await SocialAgent().run(_ctx(biz, links=[]))
    assert result.raw["present"] == []
    assert result.raw["available"] is False
    assert "unknown" in result.notes.lower()
    assert result.scores == {}  # no fabricated presence score
