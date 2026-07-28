"""Tests for Racing Post shared traffic guard."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_rp_global_trip_expires(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_RACING_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("HIBS_RP_TRIP_TTL_HOURS", "1")
    from hibs_racing.ingest import rp_traffic_guard as guard

    old = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    guard._save_state({"trip": {"at": old, "reason": "test"}})
    assert guard.global_trip_active() is False


def test_rp_live_blocked_when_tripped(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_RACING_CACHE_DIR", str(tmp_path))
    monkeypatch.setenv("EMAIL", "a@b.com")
    monkeypatch.setenv("ACCESS_TOKEN", "tok")
    from hibs_racing.ingest import rp_traffic_guard as guard

    guard.record_rate_limit(reason="test")
    assert guard.rp_live_traffic_allowed() is False
