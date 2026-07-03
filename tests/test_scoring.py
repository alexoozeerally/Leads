"""Tests for the Phase-1 opportunity scoring."""

from __future__ import annotations

from app.schemas.audit import AuditResult, ScoreEntry, WebsiteState
from app.services.scoring import opportunity_from_results


def _audit(quality_ratio: float) -> dict[str, AuditResult]:
    # A single dimension scoring `quality_ratio * 10` out of 10.
    return {
        "vision": AuditResult(
            module="vision",
            scores={"q": ScoreEntry(value=quality_ratio * 10, max=10, explanation="test")},
        )
    }


def test_no_site_is_high_opportunity():
    assert opportunity_from_results(WebsiteState.NO_SITE, {}) == 90.0
    assert opportunity_from_results(WebsiteState.PARKED, {}) == 90.0
    assert opportunity_from_results(WebsiteState.BROKEN, {}) == 90.0


def test_poor_site_scores_higher_than_good_site():
    poor = opportunity_from_results(WebsiteState.OK, _audit(0.2))
    good = opportunity_from_results(WebsiteState.OK, _audit(0.9))
    assert poor > good
    assert poor == 80.0  # (1 - 0.2) * 100
    assert good == 10.0


def test_no_measurable_scores_is_neutral():
    assert opportunity_from_results(WebsiteState.OK, {}) == 50.0


def test_gbp_and_social_do_not_affect_opportunity():
    # A strong GBP/social presence must not lower the website opportunity score;
    # only auditor+vision quality drives it.
    base = _audit(0.2)  # a poor site
    with_context = {
        **base,
        "gbp": AuditResult(
            module="gbp",
            scores={"reviews": ScoreEntry(value=10, max=10, explanation="great reviews")},
        ),
        "social": AuditResult(
            module="social",
            scores={"presence": ScoreEntry(value=10, max=10, explanation="lots of socials")},
        ),
    }
    assert opportunity_from_results(WebsiteState.OK, base) == opportunity_from_results(
        WebsiteState.OK, with_context
    )
