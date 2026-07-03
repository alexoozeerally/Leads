"""Tests for the health endpoint and DB persistence round-trip."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.database.repositories.business_repo import BusinessRepository
from app.main import app
from app.schemas import Business


@pytest.mark.asyncio
async def test_health_endpoint(db_engine):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["database"]["ok"] is True
    assert body["anthropic"] == "mock"


@pytest.mark.asyncio
async def test_business_upsert_round_trip(session):
    repo = BusinessRepository(session)
    biz = Business(
        name="Bristol Boilers", source_provider="csv", website="https://bristolboilers.co.uk"
    )
    rec = await repo.upsert(biz)
    await session.commit()
    assert rec.id is not None

    again = await repo.get_by_dedupe_key(biz.dedupe_key())
    assert again is not None
    assert again.name == "Bristol Boilers"


@pytest.mark.asyncio
async def test_upsert_never_blanks_known_data(session):
    repo = BusinessRepository(session)
    full = Business(
        name="Cardiff Cafe",
        source_provider="csv",
        website="https://cardiffcafe.example",
        phone="+44 29 2000 0000",
    )
    await repo.upsert(full)
    await session.commit()

    # A later, sparser record for the same business must not wipe the phone.
    sparse = Business(
        name="Cardiff Cafe", source_provider="osm", website="https://cardiffcafe.example"
    )
    rec = await repo.upsert(sparse)
    await session.commit()
    assert rec.phone == "+44 29 2000 0000"
