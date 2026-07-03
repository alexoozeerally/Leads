"""Tests for the re-audit freshness / de-duplication policy."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from app.services.freshness import decide


def _audit(days_ago: int):
    return SimpleNamespace(created_at=datetime.now(UTC) - timedelta(days=days_ago))


def test_never_audited_is_audited():
    d = decide(None, reaudit_after_days=30, now=datetime.now(UTC))
    assert d.should_audit is True
    assert "never" in d.reason


def test_fresh_is_skipped():
    now = datetime.now(UTC)
    d = decide(_audit(days_ago=5), reaudit_after_days=30, now=now)
    assert d.should_audit is False
    assert "fresh" in d.reason
    assert d.next_reaudit_at is not None


def test_stale_is_reaudited():
    now = datetime.now(UTC)
    d = decide(_audit(days_ago=40), reaudit_after_days=30, now=now)
    assert d.should_audit is True
    assert "stale" in d.reason


def test_force_overrides_freshness():
    now = datetime.now(UTC)
    d = decide(_audit(days_ago=1), reaudit_after_days=30, now=now, force=True)
    assert d.should_audit is True
    assert "forced" in d.reason


def test_naive_timestamp_is_treated_as_utc():
    now = datetime.now(UTC)
    naive = SimpleNamespace(created_at=datetime.utcnow() - timedelta(days=2))
    d = decide(naive, reaudit_after_days=30, now=now)
    assert d.should_audit is False  # 2 days old -> fresh, no crash on naive datetime
