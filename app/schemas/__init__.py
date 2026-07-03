"""Pydantic contracts — the shared types every layer agrees on."""

from app.schemas.audit import AuditResult, ScoreEntry, WebsiteState
from app.schemas.business import Business, DiscoveryQuery
from app.schemas.context import AuditContext, CrawlResult
from app.schemas.lead_score import Deduction, LeadScore, Priority

__all__ = [
    "AuditContext",
    "AuditResult",
    "Business",
    "CrawlResult",
    "Deduction",
    "DiscoveryQuery",
    "LeadScore",
    "Priority",
    "ScoreEntry",
    "WebsiteState",
]
