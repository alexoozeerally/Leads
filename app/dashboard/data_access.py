"""Read-side helpers for the dashboard.

Streamlit is synchronous, so these wrap the async repositories behind a simple
blocking API. Kept separate from the Streamlit view so the data layer stays
testable without a running UI.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.database.models.audit import AuditRecord
from app.database.models.business import BusinessRecord
from app.database.repositories.lead_repo import LeadRepository
from app.database.session import session_scope


@dataclass
class LeadRow:
    business_id: int
    name: str
    category: str | None
    website: str | None
    postcode: str | None
    website_state: str
    opportunity_score: float | None
    notes: str
    desktop_screenshot: str | None
    mobile_screenshot: str | None
    module_results: dict
    lead_score: dict | None = None  # full LeadScore payload
    draft: dict | None = (
        None  # {id, subject, email_body, follow_up, linkedin, lawful_basis, approved}
    )


async def _fetch_latest_leads() -> list[LeadRow]:
    async with session_scope() as session:
        businesses = (
            (await session.execute(select(BusinessRecord).order_by(BusinessRecord.name)))
            .scalars()
            .all()
        )
        rows: list[LeadRow] = []
        for biz in businesses:
            audit = (
                await session.execute(
                    select(AuditRecord)
                    .where(AuditRecord.business_id == biz.id)
                    .options(selectinload(AuditRecord.screenshots))
                    .order_by(AuditRecord.version.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            desktop = mobile = None
            module_results: dict = {}
            state = "unknown"
            opportunity = None
            notes = ""
            if audit is not None:
                state = audit.website_state
                opportunity = audit.opportunity_score
                notes = audit.notes
                module_results = audit.module_results or {}
                for shot in audit.screenshots:
                    if shot.viewport == "desktop":
                        desktop = shot.path
                    elif shot.viewport == "mobile":
                        mobile = shot.path

            lead_score_payload = None
            draft_payload = None
            score = await LeadRepository(session).latest_score_for_business(biz.id)
            if score is not None:
                lead_score_payload = score.payload
                if score.drafts:
                    d = score.drafts[0]
                    draft_payload = {
                        "id": d.id,
                        "subject": d.subject,
                        "email_body": d.email_body,
                        "follow_up": d.follow_up,
                        "linkedin_message": d.linkedin_message,
                        "lawful_basis_note": d.lawful_basis_note,
                        "approved": d.approved,
                    }

            rows.append(
                LeadRow(
                    business_id=biz.id,
                    name=biz.name,
                    category=biz.category,
                    website=biz.website,
                    postcode=biz.postcode,
                    website_state=state,
                    opportunity_score=opportunity,
                    notes=notes,
                    desktop_screenshot=desktop,
                    mobile_screenshot=mobile,
                    module_results=module_results,
                    lead_score=lead_score_payload,
                    draft=draft_payload,
                )
            )
        rows.sort(key=lambda r: r.opportunity_score or -1, reverse=True)
        return rows


def fetch_latest_leads() -> list[LeadRow]:
    """Blocking wrapper used by the Streamlit view."""
    return asyncio.run(_fetch_latest_leads())


async def _set_draft_approved(draft_id: int, approved: bool) -> None:
    async with session_scope() as session:
        await LeadRepository(session).set_draft_approved(draft_id, approved)


def set_draft_approved(draft_id: int, approved: bool) -> None:
    """Approve or un-approve a drafted outreach (human action; nothing is sent)."""
    asyncio.run(_set_draft_approved(draft_id, approved))
