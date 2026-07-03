"""Repository for audit runs and their screenshots."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database.models.audit import AuditRecord, ScreenshotRecord


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def next_version(self, business_id: int) -> int:
        result = await self._session.execute(
            select(func.max(AuditRecord.version)).where(AuditRecord.business_id == business_id)
        )
        current = result.scalar_one_or_none()
        return (current or 0) + 1

    async def create(
        self,
        *,
        business_id: int,
        website_state: str,
        final_url: str | None,
        opportunity_score: float | None,
        module_results: dict,
        crawl_summary: dict,
        notes: str = "",
    ) -> AuditRecord:
        record = AuditRecord(
            business_id=business_id,
            version=await self.next_version(business_id),
            website_state=website_state,
            final_url=final_url,
            opportunity_score=opportunity_score,
            module_results=module_results,
            crawl_summary=crawl_summary,
            notes=notes,
        )
        self._session.add(record)
        await self._session.flush()
        return record

    async def add_screenshot(self, audit_id: int, viewport: str, path: str) -> ScreenshotRecord:
        shot = ScreenshotRecord(audit_id=audit_id, viewport=viewport, path=path)
        self._session.add(shot)
        await self._session.flush()
        return shot

    async def latest_for_business(self, business_id: int) -> AuditRecord | None:
        result = await self._session.execute(
            select(AuditRecord)
            .where(AuditRecord.business_id == business_id)
            .options(selectinload(AuditRecord.screenshots))
            .order_by(AuditRecord.version.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()
