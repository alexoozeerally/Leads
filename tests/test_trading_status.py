"""Tests for the trading-status (is-it-still-open?) assessment."""

from __future__ import annotations

from app.schemas.audit import WebsiteState
from app.services.trading_status import TradingStatus, assess_trading


def test_live_site_is_active():
    a = assess_trading(website_listed=True, state=WebsiteState.OK)
    assert a.status is TradingStatus.ACTIVE
    assert "live" in a.reason.lower()


def test_parked_domain_is_likely_closed():
    a = assess_trading(website_listed=True, state=WebsiteState.PARKED)
    assert a.status is TradingStatus.LIKELY_CLOSED
    assert "parked" in a.reason.lower() or "sale" in a.reason.lower()


def test_listed_but_dead_site_is_likely_closed():
    for state in (WebsiteState.BROKEN, WebsiteState.REDIRECT_LOOP, WebsiteState.NO_SITE):
        a = assess_trading(website_listed=True, state=state)
        assert a.status is TradingStatus.LIKELY_CLOSED, state


def test_no_website_listed_is_unknown_not_closed():
    # No site to verify => honest 'unknown', never a fabricated 'active'/'closed'.
    a = assess_trading(website_listed=False, state=WebsiteState.NO_SITE)
    assert a.status is TradingStatus.UNKNOWN
    assert a.reason


def test_responding_but_neglected_site_is_unknown():
    for state in (WebsiteState.UNDER_CONSTRUCTION, WebsiteState.INVALID_SSL):
        a = assess_trading(website_listed=True, state=state)
        assert a.status is TradingStatus.UNKNOWN, state


def test_broken_site_with_no_listing_is_unknown():
    # A broken result with no website listed can't be pinned on the business.
    a = assess_trading(website_listed=False, state=WebsiteState.BROKEN)
    assert a.status is TradingStatus.UNKNOWN
