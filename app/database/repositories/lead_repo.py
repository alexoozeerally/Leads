"""Repository for lead scores, outreach drafts, and the suppression list."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models.lead import LeadScoreRecord, OutreachDraft, SuppressionEntry


class LeadRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_score(
        self,
        *,
        business_id: int,
        audit_id: int | None,
        opportunity_score: float,
        priority: str,
        likelihood_of_purchase: float,
        estimated_budget: str | None,
        estimated_project_value: str | None,
        summary: str,
        payload: dict,
    ) -> LeadScoreRecord:
        record = LeadScoreRecord(
            business_id=business_id,
            audit_id=audit_id,
            opportunity_score=opportunity_score,
            priority=priority,
            likelihood_of_purchase=likelihood_of_purchase,
            estimated_budget=estimated_budget,
            estimated_project_value=estimated_project_value,
            summary=summary,
            payload=payload,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def add_draft(
        self,
        *,
        lead_score_id: int,
        subject: str,
        email_body: str,
        follow_up: str,
        linkedin_message: str,
        lawful_basis_note: str,
        payload: dict,
    ) -> OutreachDraft:
        draft = OutreachDraft(
            lead_score_id=lead_score_id,
            subject=subject,
            email_body=email_body,
            follow_up=follow_up,
            linkedin_message=linkedin_message,
            lawful_basis_note=lawful_basis_note,
            payload=payload,
            approved=False,  # never auto-approved
        )
        self._session.add(draft)
        await self._session.flush()
        return draft

    async def get_draft(self, draft_id: int) -> OutreachDraft | None:
        return await self._session.get(OutreachDraft, draft_id)

    async def set_draft_approved(self, draft_id: int, approved: bool) -> OutreachDraft | None:
        draft = await self._session.get(OutreachDraft, draft_id)
        if draft is not None:
            draft.approved = approved
            await self._session.flush()
        return draft

    async def latest_score_for_business(self, business_id: int) -> LeadScoreRecord | None:
        result = await self._session.execute(
            select(LeadScoreRecord)
            .where(LeadScoreRecord.business_id == business_id)
            .options(selectinload(LeadScoreRecord.drafts))
            .order_by(LeadScoreRecord.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()


class SuppressionRepository:
    """Do-not-contact list — checked before any draft is surfaced for approval."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, match_value: str, reason: str = "") -> SuppressionEntry:
        entry = SuppressionEntry(match_value=match_value.strip().lower(), reason=reason)
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def all_values(self) -> set[str]:
        result = await self._session.execute(select(SuppressionEntry.match_value))
        return {v.lower() for v in result.scalars().all()}

    async def is_suppressed(
        self, *, email: str | None, phone: str | None, website: str | None
    ) -> bool:
        values = await self.all_values()
        if not values:
            return False
        candidates: list[str] = []
        if email:
            candidates.append(email.lower())
            candidates.append(email.split("@")[-1].lower())  # domain
        if phone:
            candidates.append("".join(ch for ch in phone if ch.isdigit()))
        if website:
            host = website.lower().replace("https://", "").replace("http://", "").split("/")[0]
            candidates.append(host.removeprefix("www."))
        return any(c in values for c in candidates if c)
