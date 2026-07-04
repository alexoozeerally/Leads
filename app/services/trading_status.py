"""Is this business still trading?

Directories like OpenStreetMap keep listings long after a business has closed,
so a "great" lead (no/weak website) is worthless if the firm no longer exists.
We cannot confirm closure from Google (scraping it breaks their ToS), so we
judge trading status from evidence we *can* gather honestly — chiefly whether
the business's website is actually live:

- a website that loads normally is strong evidence the business still trades;
- a parked / for-sale domain, or a listed website that no longer resolves, is a
  classic sign the business has folded and let its domain lapse;
- with no website at all, map data alone cannot confirm the business still
  trades, so we say so plainly (``unknown``) rather than guess.

Nothing here is fabricated: every verdict carries the evidence it rests on, and
absence of evidence yields ``unknown``, never a false "active"/"closed".
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.schemas.audit import WebsiteState


class TradingStatus(StrEnum):
    """How confident we are that the business is still operating."""

    ACTIVE = "active"
    LIKELY_CLOSED = "likely_closed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class TradingAssessment:
    status: TradingStatus
    reason: str


# States that mean "a website was listed but it is dead" — a domain someone once
# paid for and stopped renewing, which very often means the business has closed.
_DEAD_SITE_STATES = {
    WebsiteState.NO_SITE,  # listed URL no longer resolves
    WebsiteState.BROKEN,
    WebsiteState.REDIRECT_LOOP,
}


def assess_trading(*, website_listed: bool, state: WebsiteState) -> TradingAssessment:
    """Judge whether a business is still trading from its web presence.

    ``website_listed`` is whether the directory gave us a website URL at all;
    ``state`` is what the crawler found when it visited it.
    """
    # A live website is the strongest ToS-clean evidence a business still trades.
    if state == WebsiteState.OK:
        return TradingAssessment(
            TradingStatus.ACTIVE,
            "Website is live and loads normally — strong evidence the business is still trading.",
        )

    # A parked / for-sale domain almost always means the firm has folded.
    if state == WebsiteState.PARKED:
        return TradingAssessment(
            TradingStatus.LIKELY_CLOSED,
            "The listed domain is parked / advertised for sale — usually means the business has "
            "closed and let the domain lapse. Verify before contacting.",
        )

    # A website was listed but it no longer loads at all.
    if website_listed and state in _DEAD_SITE_STATES:
        return TradingAssessment(
            TradingStatus.LIKELY_CLOSED,
            "A website was listed but it no longer loads — often a sign the business has closed "
            "(could also be a temporary outage). Verify before contacting.",
        )

    # The server responded but the site is unfinished or misconfigured: someone
    # is still paying for the domain, so the business is probably around but the
    # site is neglected. We can't be certain, so this is 'unknown', not 'active'.
    if state in (WebsiteState.UNDER_CONSTRUCTION, WebsiteState.INVALID_SSL):
        return TradingAssessment(
            TradingStatus.UNKNOWN,
            "The site responds but is unfinished or misconfigured — the domain is live, but that "
            "alone can't confirm the business is trading. Worth a quick check.",
        )

    # No working website to verify against (e.g. never had one on the listing).
    return TradingAssessment(
        TradingStatus.UNKNOWN,
        "No working website to verify against — directory listings can outlive the business, so "
        "confirm it is still trading before reaching out.",
    )
