"""Shared pytest fixtures.

The whole suite runs offline: an in-memory/file SQLite database and a mock
Anthropic client. No network, no keys, no Postgres required.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

# Force a throwaway SQLite DB + mock AI before any app module reads settings.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test_leadfinder.db")
os.environ.setdefault("ANTHROPIC_API_KEY", "")
os.environ.setdefault("ENVIRONMENT", "test")

from app.config.settings import get_settings  # noqa: E402
from app.database.models import Base  # noqa: E402
from app.database.session import get_engine, get_sessionmaker, reset_engine  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _settings_cache_clear():
    get_settings.cache_clear()
    yield


@pytest_asyncio.fixture
async def db_engine() -> AsyncIterator[None]:
    """Create all tables on a fresh engine, drop them afterwards."""
    await reset_engine()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await reset_engine()


@pytest_asyncio.fixture
async def session(db_engine):
    """Yield an AsyncSession bound to the test database."""
    maker = get_sessionmaker()
    async with maker() as s:
        yield s
