"""Tests for lead qualification (LeadScorer)."""

from __future__ import annotations

from app.schemas.audit import AuditResult, ScoreEntry, WebsiteState
from app.schemas.business import Business
from app.schemas.competitor import CompetitorReport
from app.schemas.lead_score import Priority
from app.services.lead_scoring import LeadScorer


def _auditor(quality: float, state: str = "ok") -> AuditResult:
    return AuditResult(
        module="auditor",
        scores={"x": ScoreEntry(value=quality * 10, max=10, explanation="test")},
        raw={"state": state, "signals": {"has_tel_link": True}},
    )


def test_no_site_is_hot_with_new_site_budget():
    biz = Business(name="No Web Co", source_provider="csv", phone="0117", review_count=40)
    ls = LeadScorer().score(
        business=biz,
        website_state=WebsiteState.NO_SITE,
        opportunity_score=90.0,
        results={"auditor": _auditor(0.0, state="no_site")},
    )
    assert ls.priority is Priority.HOT
    assert ls.estimated_budget == "£2,000–£5,000"
    assert any(d.dimension == "need" and d.points == 45.0 for d in ls.rationale)
    # Likelihood reflects reachability + activity.
    assert ls.likelihood_of_purchase > 0.7


def test_strong_site_is_cold_with_improve_budget():
    biz = Business(name="Great Co", source_provider="csv", website="https://x.example")
    ls = LeadScorer().score(
        business=biz,
        website_state=WebsiteState.OK,
        opportunity_score=20.0,
        results={"auditor": _auditor(0.9)},
    )
    assert ls.priority is Priority.COLD
    assert ls.estimated_budget == "£800–£2,000"  # improvements, not a rebuild


def test_weak_site_gets_redesign_band():
    biz = Business(name="Weak Co", source_provider="csv", website="https://x.example")
    ls = LeadScorer().score(
        business=biz,
        website_state=WebsiteState.OK,
        opportunity_score=60.0,
        results={"auditor": _auditor(0.3)},
    )
    assert ls.estimated_budget == "£1,500–£4,000"  # redesign band
    assert ls.priority is Priority.WARM


def test_every_estimate_carries_a_rationale():
    biz = Business(name="Co", source_provider="csv", website="https://x.example")
    ls = LeadScorer().score(
        business=biz,
        website_state=WebsiteState.OK,
        opportunity_score=50.0,
        results={"auditor": _auditor(0.5)},
    )
    dims = {d.dimension for d in ls.rationale}
    assert {"budget", "likelihood"} <= dims
    assert all(d.rationale for d in ls.rationale)


def test_competitive_pressure_recorded_in_rationale():
    biz = Business(name="Co", source_provider="csv", website="https://x.example", review_count=10)
    report = CompetitorReport(competitors_found=3, competitive_pressure=0.4)
    ls = LeadScorer().score(
        business=biz,
        website_state=WebsiteState.OK,
        opportunity_score=55.0,
        results={"auditor": _auditor(0.4)},
        competitor=report,
    )
    assert any(d.dimension == "competition" for d in ls.rationale)
