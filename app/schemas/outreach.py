"""Outreach draft contract.

A drafted outreach package: subject, email, follow-up, LinkedIn message. It must
contain exactly **two genuine opportunities + one compliment + one clear CTA**,
with no exaggerated claims. It is a *draft* — a human approves before sending.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class OutreachContent(BaseModel):
    """Validated outreach content returned by the email generator."""

    subject: str = Field(..., min_length=1, max_length=200)
    email_body: str = Field(..., min_length=1)
    follow_up: str = Field(..., min_length=1)
    linkedin_message: str = Field(..., min_length=1)
    compliment: str = Field(..., min_length=1, description="One genuine, specific compliment.")
    opportunities: list[str] = Field(..., description="Exactly two genuine opportunities.")
    call_to_action: str = Field(..., min_length=1)

    @field_validator("opportunities")
    @classmethod
    def _exactly_two(cls, v: list[str]) -> list[str]:
        if len(v) != 2:
            raise ValueError("outreach must reference exactly two opportunities")
        if any(not o.strip() for o in v):
            raise ValueError("opportunities must be non-empty")
        return v
