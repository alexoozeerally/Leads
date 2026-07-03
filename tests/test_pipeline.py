"""End-to-end pipeline test with fakes — real SQLite, no browser, no network."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from app.agents.llm_client import MockLLMClient
from app.agents.vision import VisionAgent
from app.business_providers.base import BusinessProvider
from app.database.models.audit import AuditRecord, ScreenshotRecord
from app.database.models.business import BusinessRecord
from app.database.session import session_scope
from app.schemas.audit import WebsiteState
from app.schemas.business import Business, DiscoveryQuery
from app.schemas.context import CrawlResult
from app.services.pipeline import LeadPipeline


class FakeProvider(BusinessProvider):
    name = "fake"

    def __init__(self, businesses: list[Business]) -> None:
        self._businesses = businesses

    async def search(self, query: DiscoveryQuery) -> list[Business]:
        return self._businesses


class FakeCrawler:
    """Returns a preset CrawlResult keyed by website; no real browser."""

    def __init__(self, mapping: dict[str | None, CrawlResult]) -> None:
        self._mapping = mapping

    async def crawl(self, website: str | None) -> CrawlResult:
        return self._mapping.get(website, CrawlResult(url="", state=WebsiteState.NO_SITE))


@pytest.mark.asyncio
async def test_pipeline_persists_businesses_audits_screenshots(db_engine, tmp_path):
    shot = tmp_path / "d.png"
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")

    good = Business(name="Good Co", source_provider="fake", website="https://good.example")
    nosite = Business(name="No Web Co", source_provider="fake")
    businesses = [good, nosite]

    crawl_map = {
        "https://good.example": CrawlResult(
            url="https://good.example",
            final_url="https://good.example",
            state=WebsiteState.OK,
            status_code=200,
            text="A perfectly nice website with plenty of content.",
            desktop_screenshot=str(shot),
            mobile_screenshot=str(shot),
        ),
        None: CrawlResult(url="", state=WebsiteState.NO_SITE),
    }

    pipeline = LeadPipeline(
        provider=FakeProvider(businesses),
        crawler=FakeCrawler(crawl_map),
        modules=[VisionAgent(client=MockLLMClient())],
    )

    result = await pipeline.run(DiscoveryQuery(industry="", limit=10))

    assert len(result.outcomes) == 2
    by_name = {o.business.name: o for o in result.outcomes}
    # No-site business gets the automatic high opportunity score.
    assert by_name["No Web Co"].opportunity_score == 90.0
    assert by_name["No Web Co"].state == WebsiteState.NO_SITE

    async with session_scope() as session:
        biz_count = await session.scalar(select(func.count()).select_from(BusinessRecord))
        audit_count = await session.scalar(select(func.count()).select_from(AuditRecord))
        shot_count = await session.scalar(select(func.count()).select_from(ScreenshotRecord))
    assert biz_count == 2
    assert audit_count == 2
    assert shot_count == 2  # only the good site had screenshots


@pytest.mark.asyncio
async def test_pipeline_reaudit_increments_version(db_engine, tmp_path):
    biz = Business(name="Repeat Co", source_provider="fake", website="https://repeat.example")
    crawl_map = {
        "https://repeat.example": CrawlResult(
            url="https://repeat.example", state=WebsiteState.OK, status_code=200, text="hello world"
        )
    }
    pipeline = LeadPipeline(
        provider=FakeProvider([biz]),
        crawler=FakeCrawler(crawl_map),
        modules=[VisionAgent(client=MockLLMClient())],
    )
    await pipeline.process_all([biz])
    await pipeline.process_all([biz])  # second audit of the same business

    async with session_scope() as session:
        versions = (
            (await session.execute(select(AuditRecord.version).order_by(AuditRecord.version)))
            .scalars()
            .all()
        )
        biz_count = await session.scalar(select(func.count()).select_from(BusinessRecord))
    assert versions == [1, 2]  # audit history is versioned
    assert biz_count == 1  # de-duplicated to one business
