"""Audit contracts: the shape every audit/vision/analysis agent produces.

Every score carries an explanation — there are no naked numbers anywhere in the
system. If evidence is absent, the explanation says so and the value reflects
"unknown", never an invented figure.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class WebsiteState(StrEnum):
    """Explicitly-handled states of a business's web presence."""

    OK = "ok"
    NO_SITE = "no_site"
    BROKEN = "broken"
    UNDER_CONSTRUCTION = "under_construction"
    REDIRECT_LOOP = "redirect_loop"
    INVALID_SSL = "invalid_ssl"
    PARKED = "parked"
    UNKNOWN = "unknown"


class ScoreEntry(BaseModel):
    """A single scored dimension. Every score must explain itself."""

    value: float = Field(..., ge=0)
    max: float = Field(..., gt=0)
    explanation: str = Field(..., min_length=1, description="Evidence-based rationale.")

    @property
    def ratio(self) -> float:
        return self.value / self.max if self.max else 0.0


class AuditResult(BaseModel):
    """Uniform result returned by every :class:`AuditModule`.

    ``scores`` maps a dimension name to its :class:`ScoreEntry`. ``raw`` keeps the
    unparsed agent payload for auditing/debugging; ``notes`` is a short summary.
    """

    module: str = Field(..., description="Name of the module that produced this result.")
    scores: dict[str, ScoreEntry] = Field(default_factory=dict)
    notes: str = ""
    raw: dict = Field(default_factory=dict)

    def total(self) -> tuple[float, float]:
        """Return (sum of values, sum of maxima) across all scores."""
        return (
            sum(s.value for s in self.scores.values()),
            sum(s.max for s in self.scores.values()),
        )
