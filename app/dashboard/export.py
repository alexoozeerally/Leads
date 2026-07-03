"""CSV export for leads — a pure, testable transform over LeadRow objects."""

from __future__ import annotations

import csv
import io
from collections.abc import Iterable

from app.dashboard.data_access import LeadRow

EXPORT_COLUMNS = [
    "name",
    "category",
    "postcode",
    "website",
    "website_state",
    "opportunity_score",
    "priority",
    "likelihood_of_purchase",
    "estimated_budget",
    "estimated_project_value",
    "has_draft",
    "draft_approved",
    "summary",
]


def _row_dict(lead: LeadRow) -> dict:
    ls = lead.lead_score or {}
    draft = lead.draft or {}
    return {
        "name": lead.name,
        "category": lead.category or "",
        "postcode": lead.postcode or "",
        "website": lead.website or "",
        "website_state": lead.website_state,
        "opportunity_score": lead.opportunity_score if lead.opportunity_score is not None else "",
        "priority": ls.get("priority", ""),
        "likelihood_of_purchase": ls.get("likelihood_of_purchase", ""),
        "estimated_budget": ls.get("estimated_budget", "") or "",
        "estimated_project_value": ls.get("estimated_project_value", "") or "",
        "has_draft": bool(draft),
        "draft_approved": draft.get("approved", False) if draft else False,
        "summary": ls.get("summary", ""),
    }


def leads_to_csv(leads: Iterable[LeadRow]) -> str:
    """Serialise leads to CSV text with a stable column order."""
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=EXPORT_COLUMNS)
    writer.writeheader()
    for lead in leads:
        writer.writerow(_row_dict(lead))
    return buffer.getvalue()
