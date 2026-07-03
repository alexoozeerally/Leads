"""Pure search / filter / sort helpers for the dashboard (testable without UI)."""

from __future__ import annotations

from dataclasses import dataclass

from app.dashboard.data_access import LeadRow

SORT_OPTIONS = {
    "Opportunity (high→low)": ("opportunity", True),
    "Opportunity (low→high)": ("opportunity", False),
    "Likelihood (high→low)": ("likelihood", True),
    "Name (A→Z)": ("name", False),
}


@dataclass
class LeadFilter:
    search: str = ""
    priorities: tuple[str, ...] = ()
    min_score: float = 0.0
    only_with_draft: bool = False
    sort: str = "Opportunity (high→low)"


def _likelihood(lead: LeadRow) -> float:
    return (lead.lead_score or {}).get("likelihood_of_purchase", 0.0)


def _priority(lead: LeadRow) -> str:
    return (lead.lead_score or {}).get("priority", "")


def apply_filter(leads: list[LeadRow], f: LeadFilter) -> list[LeadRow]:
    q = f.search.strip().lower()
    out = []
    for lead in leads:
        if q:
            hay = " ".join(
                x for x in (lead.name, lead.category, lead.postcode, lead.website) if x
            ).lower()
            if q not in hay:
                continue
        if f.priorities and _priority(lead) not in f.priorities:
            continue
        if (lead.opportunity_score or 0) < f.min_score:
            continue
        if f.only_with_draft and not lead.draft:
            continue
        out.append(lead)

    key, reverse = SORT_OPTIONS.get(f.sort, ("opportunity", True))
    if key == "opportunity":
        out.sort(key=lambda le: le.opportunity_score or -1, reverse=reverse)
    elif key == "likelihood":
        out.sort(key=_likelihood, reverse=reverse)
    elif key == "name":
        out.sort(key=lambda le: le.name.lower(), reverse=reverse)
    return out
