"""Tests for the suppression (do-not-contact) list and draft approval."""

from __future__ import annotations

import pytest

from app.database.repositories.business_repo import BusinessRepository
from app.database.repositories.lead_repo import LeadRepository, SuppressionRepository
from app.schemas.business import Business


@pytest.mark.asyncio
async def test_suppression_matches_email_domain_phone_and_website(session):
    repo = SuppressionRepository(session)
    await repo.add("blocked.example", reason="asked not to be contacted")
    await repo.add("447700900000")
    await session.commit()

    assert await repo.is_suppressed(email="a@blocked.example", phone=None, website=None)
    assert await repo.is_suppressed(email=None, phone="+44 7700 900000", website=None)
    assert await repo.is_suppressed(email=None, phone=None, website="https://www.blocked.example/x")
    assert not await repo.is_suppressed(email="a@allowed.example", phone=None, website=None)


@pytest.mark.asyncio
async def test_empty_suppression_list_never_matches(session):
    repo = SuppressionRepository(session)
    assert not await repo.is_suppressed(email="a@b.c", phone="123", website="https://b.c")


@pytest.mark.asyncio
async def test_draft_defaults_unapproved_and_can_be_approved(session):
    biz_repo = BusinessRepository(session)
    lead_repo = LeadRepository(session)
    biz = await biz_repo.upsert(Business(name="Co", source_provider="csv"))
    await session.flush()

    score = await lead_repo.create_score(
        business_id=biz.id,
        audit_id=None,
        opportunity_score=50,
        priority="Warm",
        likelihood_of_purchase=0.5,
        estimated_budget="£1k",
        estimated_project_value="£2k",
        summary="s",
        payload={},
    )
    draft = await lead_repo.add_draft(
        lead_score_id=score.id,
        subject="s",
        email_body="b",
        follow_up="f",
        linkedin_message="l",
        lawful_basis_note="note",
        payload={},
    )
    await session.commit()
    assert draft.approved is False  # never auto-approved

    updated = await lead_repo.set_draft_approved(draft.id, True)
    assert updated.approved is True
