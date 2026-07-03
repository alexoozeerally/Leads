"""Tests for the WebsiteAuditor agent."""

from __future__ import annotations

import pytest

from app.agents.auditor import CATEGORIES, WebsiteAuditor
from app.agents.link_checker import LinkCheckResult
from app.schemas.audit import WebsiteState
from app.schemas.business import Business
from app.schemas.context import AuditContext, CrawlResult

_GOOD_HTML = """
<!doctype html><html><head>
<title>Acme Plumbers — Emergency Plumbing in Bristol</title>
<meta name="description" content="Fast, friendly emergency plumbers covering Bristol. Book now.">
<meta name="viewport" content="width=device-width, initial-scale=1">
<script type="application/ld+json">{"@type":"LocalBusiness"}</script></head><body>
<nav><a href="/s">S</a><a href="/a">A</a><a href="/c">C</a></nav>
<h1>Plumbers</h1><h2>Reviews</h2>
<p>Rated 5 stars, fully insured, 20 years of experience. Book now for a free quote.
Serving 12 Corn Street, Bristol BS1 1HQ. Contact us today.</p>
<img src="a.jpg" alt="team">
<form><label for="n">N</label><input id="n"></form>
<a href="tel:01179">call</a><a href="mailto:a@b.c">mail</a>
</body></html>
"""


def _ctx(state=WebsiteState.OK, html=_GOOD_HTML, links=None):
    crawl = CrawlResult(
        url="https://acme.example/",
        final_url="https://acme.example/",
        state=state,
        status_code=200,
        html=html,
        has_https=True,
        links=links or [],
    )
    return AuditContext(business=Business(name="Acme", source_provider="csv"), crawl=crawl)


class _StubLinkChecker:
    def __init__(self, result: LinkCheckResult) -> None:
        self._result = result
        self.called_with: list[str] | None = None

    async def check(self, links: list[str]) -> LinkCheckResult:
        self.called_with = links
        return self._result


@pytest.mark.asyncio
async def test_good_site_scores_high_with_explanations():
    auditor = WebsiteAuditor(check_links=False)
    result = await auditor.run(_ctx())
    # Every category present and explained.
    for cat in CATEGORIES:
        assert cat in result.scores
        assert result.scores[cat].explanation
    assert result.scores["security"].value == 10
    assert result.scores["mobile_friendly"].value == 10
    assert result.scores["navigation"].value == 10
    assert result.scores["seo"].value >= 8


@pytest.mark.asyncio
async def test_no_site_state_is_fully_explained_zero():
    auditor = WebsiteAuditor(check_links=False)
    result = await auditor.run(_ctx(state=WebsiteState.NO_SITE, html=""))
    assert all(s.value == 0 for s in result.scores.values())
    assert all(s.explanation for s in result.scores.values())
    assert "no website" in result.notes.lower()


@pytest.mark.asyncio
async def test_broken_links_only_checks_internal_links():
    stub = _StubLinkChecker(LinkCheckResult(checked=1, broken=[]))
    auditor = WebsiteAuditor(link_checker=stub, check_links=True)
    links = ["https://acme.example/page1", "https://facebook.com/acme"]
    result = await auditor.run(_ctx(links=links))
    # External link excluded; only the same-host link is checked.
    assert stub.called_with == ["https://acme.example/page1"]
    assert result.scores["broken_links"].value == 10


@pytest.mark.asyncio
async def test_broken_links_penalises_when_broken():
    stub = _StubLinkChecker(LinkCheckResult(checked=2, broken=["https://acme.example/dead"]))
    auditor = WebsiteAuditor(link_checker=stub, check_links=True)
    links = ["https://acme.example/ok", "https://acme.example/dead"]
    result = await auditor.run(_ctx(links=links))
    assert result.scores["broken_links"].value < 10
    assert "broken" in result.scores["broken_links"].explanation


@pytest.mark.asyncio
async def test_invalid_ssl_state_flagged():
    auditor = WebsiteAuditor(check_links=False)
    result = await auditor.run(_ctx(state=WebsiteState.INVALID_SSL, html=""))
    assert "ssl" in result.notes.lower()
    assert result.scores["security"].value == 0
