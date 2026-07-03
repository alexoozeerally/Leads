"""ORM model for a discovered business."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.database.models.json_type import JSONEncodedDict

if TYPE_CHECKING:
    from app.database.models.audit import AuditRecord
    from app.database.models.lead import LeadScoreRecord


class BusinessRecord(Base, TimestampMixin):
    __tablename__ = "businesses"
    __table_args__ = (UniqueConstraint("dedupe_key", name="uq_business_dedupe_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dedupe_key: Mapped[str] = mapped_column(String(512), index=True)

    name: Mapped[str] = mapped_column(String(512))
    category: Mapped[str | None] = mapped_column(String(256), nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    postcode: Mapped[str | None] = mapped_column(String(32), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    website: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    rating: Mapped[float | None] = mapped_column(Float, nullable=True)
    review_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    opening_hours: Mapped[str | None] = mapped_column(Text, nullable=True)
    social_links: Mapped[dict] = mapped_column(JSONEncodedDict, default=dict)
    latitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    longitude: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_provider: Mapped[str] = mapped_column(String(64))
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    data_confidence: Mapped[float] = mapped_column(Float, default=1.0)

    audits: Mapped[list[AuditRecord]] = relationship(
        back_populates="business", cascade="all, delete-orphan", order_by="AuditRecord.id"
    )
    lead_scores: Mapped[list[LeadScoreRecord]] = relationship(
        back_populates="business", cascade="all, delete-orphan", order_by="LeadScoreRecord.id"
    )
