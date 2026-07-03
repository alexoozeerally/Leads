"""Health check router."""

from __future__ import annotations

from fastapi import APIRouter
from sqlalchemy import text

from app.config.settings import get_settings
from app.database.session import get_engine

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict:
    """Liveness + DB connectivity check."""
    settings = get_settings()
    db_ok = False
    db_error: str | None = None
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        db_ok = True
    except Exception as exc:  # pragma: no cover - depends on live DB
        db_error = str(exc)

    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.environment,
        "database": {"ok": db_ok, "error": db_error},
        "anthropic": "live" if settings.anthropic_enabled else "mock",
    }
