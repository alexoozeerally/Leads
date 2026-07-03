"""Tests for the core contracts — the types everything else depends on."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.agents.base import AuditModule
from app.business_providers.base import BusinessProvider
from app.schemas import (
    AuditContext,
    AuditResult,
    Business,
    DiscoveryQuery,
    LeadScore,
    Priority,
    ScoreEntry,
    WebsiteState,
)


def test_business_unknown_fields_stay_none():
    b = Business(name="Acme Plumbing", source_provider="csv")
    assert b.website is None
    assert b.email is None
    assert b.rating is None
    assert b.social_links == {}
    assert b.data_confidence == 1.0


def test_business_rating_bounds():
    with pytest.raises(ValidationError):
        Business(name="x", source_provider="csv", rating=9.0)


def test_business_dedupe_key_prefers_website():
    b = Business(name="Acme", source_provider="csv", website="https://www.acme.co.uk/home")
    assert b.dedupe_key() == "site:acme.co.uk"


def test_business_dedupe_key_falls_back_to_phone_then_name():
    b = Business(name="Acme", source_provider="csv", phone="+44 20 7946 0000")
    assert b.dedupe_key() == "tel:442079460000"
    b2 = Business(name="Acme Ltd", source_provider="csv", postcode="SW1A 1AA")
    assert b2.dedupe_key() == "name:acme ltd|sw1a1aa"


def test_score_entry_requires_explanation():
    with pytest.raises(ValidationError):
        ScoreEntry(value=1, max=5, explanation="")


def test_score_entry_ratio():
    assert ScoreEntry(value=3, max=6, explanation="half marks").ratio == 0.5


def test_audit_result_total():
    r = AuditResult(
        module="demo",
        scores={
            "a": ScoreEntry(value=2, max=5, explanation="ok"),
            "b": ScoreEntry(value=1, max=5, explanation="meh"),
        },
    )
    assert r.total() == (3, 10)


def test_discovery_query_is_frozen():
    q = DiscoveryQuery(industry="plumber", town="Bristol")
    with pytest.raises(ValidationError):
        q.industry = "electrician"  # type: ignore[misc]


def test_lead_score_priority_enum():
    ls = LeadScore(opportunity_score=80, likelihood_of_purchase=0.6, priority=Priority.HOT)
    assert ls.priority is Priority.HOT
    assert ls.opportunity_score == 80


def test_provider_interface_is_abstract():
    with pytest.raises(TypeError):
        BusinessProvider()  # type: ignore[abstract]


def test_audit_context_defaults_to_no_site():
    ctx = AuditContext(business=Business(name="No Web Ltd", source_provider="csv"))
    assert ctx.website_state == WebsiteState.NO_SITE


def test_audit_module_protocol_shape():
    class Dummy:
        name = "dummy"

        async def run(self, ctx: AuditContext) -> AuditResult:
            return AuditResult(module="dummy")

    assert isinstance(Dummy(), AuditModule)
