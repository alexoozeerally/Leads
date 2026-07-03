"""Competitor-analysis contracts.

A :class:`CompetitorReport` compares a lead against nearby same-industry
competitors. Everything is derived from observed data (provider fields + audits);
where a competitor's website can't be assessed, its ``website_quality`` is
``None`` (unknown) rather than a guess.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CompetitorEntry(BaseModel):
    name: str
    rating: float | None = None
    review_count: int | None = None
    has_website: bool = False
    website_quality: float | None = Field(
        default=None, description="0–1 audit quality ratio, or None if not assessed."
    )


class CompetitorReport(BaseModel):
    """The lead's standing versus its competitors, with concrete opportunities."""

    competitors_found: int = 0
    competitors: list[CompetitorEntry] = Field(default_factory=list)

    # Review standing
    review_rank: str | None = None  # e.g. "2 of 4"
    avg_competitor_reviews: float | None = None
    avg_competitor_rating: float | None = None

    # Website standing
    lead_website_quality: float | None = None
    avg_competitor_website_quality: float | None = None
    competitors_with_website: int = 0

    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    opportunities: list[str] = Field(default_factory=list)

    # 0–1: how far behind the competitive set the lead is (higher = more pressure,
    # therefore a stronger sales opportunity). Feeds the opportunity score.
    competitive_pressure: float = 0.0
    summary: str = ""
