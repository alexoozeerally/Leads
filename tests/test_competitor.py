"""Tests for competitor analysis — provider-driven, no fabrication."""

from __future__ import annotations

import pytest

from app.business_providers.base import BusinessProvider
from app.schemas.business import Business, DiscoveryQuery
from app.services.competitor import CompetitorService


class FakeProvider(BusinessProvider):
    name = "fake"

    def __init__(self, businesses: list[Business]) -> None:
        self._businesses = businesses

    async def search(self, query: DiscoveryQuery) -> list[Business]:
        return [b for b in self._businesses if (b.category or "") == query.industry]


def _dentist(name, rating, reviews, website="modern.html", postcode="BS8 2QN"):
    return Business(
        name=name,
        source_provider="fake",
        category="Dentist",
        postcode=postcode,
        rating=rating,
        review_count=reviews,
        website=website,
    )


@pytest.mark.asyncio
async def test_no_competitors_reports_cleanly():
    lead = _dentist("Solo Dental", 4.5, 100)
    service = CompetitorService(provider=FakeProvider([lead]), audit_competitor_sites=False)
    report = await service.analyse(lead, lead_website_quality=0.8)
    assert report.competitors_found == 0
    assert "no same-industry competitors" in report.summary.lower()


@pytest.mark.asyncio
async def test_ranks_and_generates_three_opportunities():
    lead = _dentist("Weak Dental", 3.8, 30)
    rivals = [
        _dentist("Strong A", 4.7, 300),
        _dentist("Strong B", 4.6, 250),
    ]
    service = CompetitorService(
        provider=FakeProvider([lead, *rivals]), audit_competitor_sites=False
    )
    report = await service.analyse(lead, lead_website_quality=0.4)
    assert report.competitors_found == 2
    # Lead is last by review volume.
    assert report.review_rank == "3 of 3"
    assert report.avg_competitor_reviews == 275.0
    # Exactly three concrete opportunities, no more no less.
    assert len(report.opportunities) == 3
    # Being behind on reviews creates competitive pressure that raises opportunity.
    assert report.competitive_pressure > 0
    # The review gap must be surfaced as one of the concrete opportunities.
    assert any("reviews" in o.lower() for o in report.opportunities)


@pytest.mark.asyncio
async def test_leader_has_strengths_and_low_pressure():
    lead = _dentist("Top Dental", 4.9, 400)
    rivals = [_dentist("Rival", 4.0, 50)]
    service = CompetitorService(
        provider=FakeProvider([lead, *rivals]), audit_competitor_sites=False
    )
    report = await service.analyse(lead, lead_website_quality=0.9)
    assert report.competitive_pressure == 0.0
    assert report.strengths
    assert len(report.opportunities) == 3  # still offers concrete next steps


@pytest.mark.asyncio
async def test_excludes_self_by_name():
    lead = _dentist("Clifton Dental", 4.3, 215)
    # The provider returns the lead itself among results; it must be excluded.
    service = CompetitorService(
        provider=FakeProvider([lead, _dentist("Rival", 4.0, 50)]),
        audit_competitor_sites=False,
    )
    report = await service.analyse(lead, lead_website_quality=0.7)
    names = [c.name for c in report.competitors]
    assert "Clifton Dental" not in names
    assert names == ["Rival"]


class _StubCrawler:
    async def crawl(self, url):
        from app.schemas.audit import WebsiteState
        from app.schemas.context import CrawlResult

        return CrawlResult(url=url, state=WebsiteState.OK, html="<html></html>")


class _StubAuditor:
    """Returns a fixed quality ratio for every competitor site."""

    def __init__(self, ratio: float) -> None:
        self._ratio = ratio

    async def run(self, ctx):
        from app.schemas.audit import AuditResult, ScoreEntry

        return AuditResult(
            module="auditor",
            scores={"x": ScoreEntry(value=self._ratio * 10, max=10, explanation="stub")},
        )


@pytest.mark.asyncio
async def test_website_gap_creates_weakness_when_competitors_audited():
    lead = _dentist("Weak Site Dental", 4.2, 200)
    rivals = [_dentist("Rival A", 4.2, 200), _dentist("Rival B", 4.2, 200)]
    service = CompetitorService(
        provider=FakeProvider([lead, *rivals]),
        crawler=_StubCrawler(),
        auditor=_StubAuditor(0.85),  # competitors have strong sites
        audit_competitor_sites=True,
    )
    report = await service.analyse(lead, lead_website_quality=0.40)  # lead's site is weak
    assert report.avg_competitor_website_quality == 0.85
    assert report.weaknesses  # the website gap is surfaced
    assert report.competitive_pressure > 0
    assert any("stronger" in o.lower() or "redesign" in o.lower() for o in report.opportunities)


@pytest.mark.asyncio
async def test_website_quality_none_when_not_audited():
    lead = _dentist("Lead", 4.0, 100)
    rival = _dentist("Rival", 4.0, 100)
    service = CompetitorService(provider=FakeProvider([lead, rival]), audit_competitor_sites=False)
    report = await service.analyse(lead, lead_website_quality=None)
    # Competitor sites weren't audited -> quality is unknown (None), not invented.
    assert all(c.website_quality is None for c in report.competitors)
    assert report.avg_competitor_website_quality is None
