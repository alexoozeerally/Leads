"""The final aggregate lead score and its supporting types.

Every deduction is explained. Budget/value/likelihood are derived from observed
evidence via documented heuristics — never guessed from thin air.
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field

from app.schemas.audit import ScoreEntry


class Priority(StrEnum):
    HOT = "Hot"
    WARM = "Warm"
    COLD = "Cold"


class Deduction(BaseModel):
    """One reason the opportunity score moved, with its evidence."""

    dimension: str
    points: float = Field(..., description="Points awarded to opportunity (higher = better lead).")
    rationale: str = Field(..., min_length=1)


class LeadScore(BaseModel):
    """Aggregate qualification of a lead as a web-design prospect."""

    dimension_scores: dict[str, ScoreEntry] = Field(default_factory=dict)
    opportunity_score: float = Field(..., ge=0, le=100)
    estimated_budget: str | None = Field(
        default=None, description="Human-readable budget band, e.g. '£1.5k–£4k'. None if unknown."
    )
    estimated_project_value: str | None = None
    likelihood_of_purchase: float = Field(..., ge=0, le=1)
    priority: Priority
    rationale: list[Deduction] = Field(default_factory=list)
    summary: str = ""
