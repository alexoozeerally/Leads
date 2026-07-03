"""Repository for :class:`BusinessRecord` — the businesses aggregate.

The repository is the only place that talks to the ORM for this aggregate; the
rest of the app works through it, decoupled from SQLAlchemy details.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.business import BusinessRecord
from app.schemas.business import Business


class BusinessRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, business_id: int) -> BusinessRecord | None:
        return await self._session.get(BusinessRecord, business_id)

    async def get_by_dedupe_key(self, dedupe_key: str) -> BusinessRecord | None:
        result = await self._session.execute(
            select(BusinessRecord).where(BusinessRecord.dedupe_key == dedupe_key)
        )
        return result.scalar_one_or_none()

    async def list(self, limit: int = 100, offset: int = 0) -> list[BusinessRecord]:
        result = await self._session.execute(
            select(BusinessRecord).order_by(BusinessRecord.id).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def upsert(self, business: Business) -> BusinessRecord:
        """Insert or update a business keyed by its dedupe key.

        Only overwrites a stored field when the incoming record has a value —
        we never blank out known data with a later provider's unknowns.
        """
        key = business.dedupe_key()
        record = await self.get_by_dedupe_key(key)
        if record is None:
            record = BusinessRecord(dedupe_key=key)
            self._session.add(record)

        incoming = business.model_dump()
        for field, value in incoming.items():
            if field == "social_links":
                if value:
                    record.social_links = {**(record.social_links or {}), **value}
                continue
            if value is not None:
                setattr(record, field, value)

        await self._session.flush()
        return record
