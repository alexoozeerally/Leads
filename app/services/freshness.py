"""Re-audit freshness / de-duplication policy.

Decides whether a business should be (re-)audited now or skipped because it was
audited recently. Keeps the "don't hammer the same site every run" rule in one
testable place, configurable via ``reaudit_after_days``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from app.database.models.audit import AuditRecord


@dataclass
class FreshnessDecision:
    should_audit: bool
    reason: str
    next_reaudit_at: datetime | None = None
    last_audited_at: datetime | None = None


def decide(
    latest_audit: AuditRecord | None,
    *,
    reaudit_after_days: int,
    now: datetime,
    force: bool = False,
) -> FreshnessDecision:
    """Return whether to audit, with a human-readable reason and re-audit date."""
    if latest_audit is None:
        return FreshnessDecision(True, "never audited before")
    if force:
        return FreshnessDecision(True, "forced re-audit", last_audited_at=latest_audit.created_at)

    last = latest_audit.created_at
    if last.tzinfo is None:
        last = last.replace(tzinfo=UTC)
    next_due = last + timedelta(days=reaudit_after_days)
    if now >= next_due:
        age = (now - last).days
        return FreshnessDecision(True, f"stale — last audited {age} day(s) ago", next_due, last)
    days_left = (next_due - now).days
    return FreshnessDecision(
        False,
        f"fresh — audited {(now - last).days} day(s) ago; re-audit in {days_left} day(s)",
        next_due,
        last,
    )
