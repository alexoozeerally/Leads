"""ORM models for the aggregate lead score and drafted outreach."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.database.models.json_type import JSONEncodedDict

if TYPE_CHECKING:
    from app.database.models.business import BusinessRecord


class LeadScoreRecord(Base, TimestampMixin):
    __tablename__ = "lead_scores"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    audit_id: Mapped[int | None] = mapped_column(
        ForeignKey("audits.id", ondelete="SET NULL"), nullable=True
    )

    opportunity_score: Mapped[float] = mapped_column(Float)
    priority: Mapped[str] = mapped_column(String(16))
    likelihood_of_purchase: Mapped[float] = mapped_column(Float)
    estimated_budget: Mapped[str | None] = mapped_column(String(64), nullable=True)
    estimated_project_value: Mapped[str | None] = mapped_column(String(64), nullable=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    payload: Mapped[dict] = mapped_column(JSONEncodedDict, default=dict)  # full LeadScore dump

    business: Mapped[BusinessRecord] = relationship(back_populates="lead_scores")
    drafts: Mapped[list[OutreachDraft]] = relationship(
        back_populates="lead_score", cascade="all, delete-orphan"
    )


class OutreachDraft(Base, TimestampMixin):
    """A drafted outreach package. Never sent automatically — requires approval."""

    __tablename__ = "outreach_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    lead_score_id: Mapped[int] = mapped_column(
        ForeignKey("lead_scores.id", ondelete="CASCADE"), index=True
    )

    subject: Mapped[str] = mapped_column(String(512), default="")
    email_body: Mapped[str] = mapped_column(Text, default="")
    follow_up: Mapped[str] = mapped_column(Text, default="")
    linkedin_message: Mapped[str] = mapped_column(Text, default="")
    lawful_basis_note: Mapped[str] = mapped_column(Text, default="")

    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSONEncodedDict, default=dict)

    lead_score: Mapped[LeadScoreRecord] = relationship(back_populates="drafts")


class SuppressionEntry(Base, TimestampMixin):
    """Do-not-contact list. Checked before any draft is surfaced for approval."""

    __tablename__ = "suppression_list"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    match_value: Mapped[str] = mapped_column(String(512), index=True)  # email/domain/phone
    reason: Mapped[str] = mapped_column(Text, default="")
