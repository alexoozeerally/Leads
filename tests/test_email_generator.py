"""Tests for the outreach email generator."""

from __future__ import annotations

import pytest

from app.agents.email_generator import EmailGenerator
from app.agents.llm_client import MockLLMClient
from app.schemas.audit import AuditResult, ScoreEntry
from app.schemas.business import Business
from app.schemas.competitor import CompetitorReport
from app.schemas.lead_score import LeadScore, Priority
from app.schemas.outreach import OutreachContent


def _lead_score() -> LeadScore:
    return LeadScore(opportunity_score=60, likelihood_of_purchase=0.6, priority=Priority.WARM)


def _auditor_no_site() -> AuditResult:
    return AuditResult(
        module="auditor",
        scores={"security": ScoreEntry(value=0, max=10, explanation="no site")},
        raw={"state": "no_site"},
    )


def _auditor_weak() -> AuditResult:
    scores = {
        "security": ScoreEntry(value=0, max=10, explanation="no https"),
        "mobile_friendly": ScoreEntry(value=1, max=10, explanation="no viewport"),
        "content": ScoreEntry(value=9, max=10, explanation="lots of content"),
    }
    return AuditResult(module="auditor", scores=scores, raw={"state": "ok"})


@pytest.mark.asyncio
async def test_draft_has_exactly_two_opportunities_and_cta():
    biz = Business(
        name="Weak Co",
        source_provider="csv",
        website="https://x.example",
        rating=4.5,
        review_count=30,
    )
    gen = EmailGenerator(client=MockLLMClient())
    content = await gen.generate(
        business=biz,
        lead_score=_lead_score(),
        results={"auditor": _auditor_weak()},
        competitor=None,
    )
    assert isinstance(content, OutreachContent)
    assert len(content.opportunities) == 2
    assert content.opportunities[0] != content.opportunities[1]  # distinct
    assert content.call_to_action
    assert content.compliment


@pytest.mark.asyncio
async def test_no_site_opportunities_are_distinct_and_relevant():
    biz = Business(name="No Web Co", source_provider="csv", rating=4.8, review_count=42)
    gen = EmailGenerator(client=MockLLMClient())
    content = await gen.generate(
        business=biz,
        lead_score=_lead_score(),
        results={"auditor": _auditor_no_site()},
        competitor=None,
    )
    assert len(set(content.opportunities)) == 2
    assert any("website" in o.lower() for o in content.opportunities)


@pytest.mark.asyncio
async def test_prefers_competitor_opportunities():
    biz = Business(name="Co", source_provider="csv", website="https://x.example")
    report = CompetitorReport(
        competitors_found=2,
        opportunities=["Rivals rank higher — target their local search terms.", "Add reviews."],
        strengths=["Your rating beats the local average."],
    )
    gen = EmailGenerator(client=MockLLMClient())
    content = await gen.generate(
        business=biz,
        lead_score=_lead_score(),
        results={"auditor": _auditor_weak()},
        competitor=report,
    )
    assert content.opportunities[0].startswith("Rivals rank higher")
    # Compliment is a real competitive strength, not invented flattery.
    assert "beats the local average" in content.compliment


@pytest.mark.asyncio
async def test_email_includes_unsubscribe():
    biz = Business(name="Co", source_provider="csv", website="https://x.example")
    gen = EmailGenerator(client=MockLLMClient())
    content = await gen.generate(
        business=biz,
        lead_score=_lead_score(),
        results={"auditor": _auditor_weak()},
        competitor=None,
    )
    assert "unsubscribe" in content.email_body.lower()
    assert "unsubscribe" in content.follow_up.lower()


@pytest.mark.asyncio
async def test_validation_rejects_wrong_opportunity_count():
    import pytest as _pytest
    from pydantic import ValidationError

    with _pytest.raises(ValidationError):
        OutreachContent(
            subject="s",
            email_body="b",
            follow_up="f",
            linkedin_message="l",
            compliment="c",
            opportunities=["only one"],
            call_to_action="cta",
        )
