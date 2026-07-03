"""ORM models for audit runs and their screenshots.

An ``AuditRecord`` is one full audit pass for a business (versioned by run). It
stores per-module scores as JSON and links to captured screenshots.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database.base import Base, TimestampMixin
from app.database.models.json_type import JSONEncodedDict

if TYPE_CHECKING:
    from app.database.models.business import BusinessRecord


class AuditRecord(Base, TimestampMixin):
    __tablename__ = "audits"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    business_id: Mapped[int] = mapped_column(
        ForeignKey("businesses.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer, default=1)

    website_state: Mapped[str] = mapped_column(String(32), default="unknown")
    final_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    opportunity_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Full structured payload: {module_name: AuditResult.model_dump()}
    module_results: Mapped[dict] = mapped_column(JSONEncodedDict, default=dict)
    crawl_summary: Mapped[dict] = mapped_column(JSONEncodedDict, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")

    business: Mapped[BusinessRecord] = relationship(back_populates="audits")
    screenshots: Mapped[list[ScreenshotRecord]] = relationship(
        back_populates="audit", cascade="all, delete-orphan"
    )


class ScreenshotRecord(Base, TimestampMixin):
    __tablename__ = "screenshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    audit_id: Mapped[int] = mapped_column(ForeignKey("audits.id", ondelete="CASCADE"), index=True)
    viewport: Mapped[str] = mapped_column(String(16))  # "desktop" | "mobile"
    path: Mapped[str] = mapped_column(String(1024))

    audit: Mapped[AuditRecord] = relationship(back_populates="screenshots")
