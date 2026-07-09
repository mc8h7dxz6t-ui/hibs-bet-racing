"""Tests for Matchbook poll gate (Mac/VPS owner, rate limit, 429 trip)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def _write_state(tmp_path: Path, data: dict) -> None:
    cache = tmp_path / "data" / ".cache"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "matchbook_guard_v1.json").write_text(json.dumps(data), encoding="utf-8")


def test_matchbook_configured_accepts_user_alias(monkeypatch):
    monkeypatch.setenv("MATCHBOOK_USER", "alice")
    monkeypatch.setenv("MATCHBOOK_PASSWORD", "secret")
    from hibs_racing.matchbook_guard import matchbook_configured

    assert matchbook_configured() is True


def test_mac_quotes_fresh_blocks_vps_poll(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_RACING_CACHE_DIR", str(tmp_path / "data" / ".cache"))
    monkeypatch.setenv("HIBS_RACING_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("MATCHBOOK_USERNAME", "alice")
    monkeypatch.setenv("MATCHBOOK_PASSWORD", "secret")
    monkeypatch.setenv("HIBS_MATCHBOOK_POLL_OWNER", "vps")

    marker = tmp_path / "data" / ".cache" / "mac_odds_publish.json"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("{}", encoding="utf-8")

    from hibs_racing.matchbook_guard import matchbook_traffic_allowed

    assert matchbook_traffic_allowed() is False


def test_global_trip_blocks_poll(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_RACING_CACHE_DIR", str(tmp_path / "data" / ".cache"))
    monkeypatch.setenv("MATCHBOOK_USERNAME", "alice")
    monkeypatch.setenv("MATCHBOOK_PASSWORD", "secret")
    _write_state(
        tmp_path,
        {
            "trip": {
                "at": datetime.now(timezone.utc).isoformat(),
                "status": 429,
                "reason": "events",
            }
        },
    )

    from hibs_racing.matchbook_guard import global_trip_active, matchbook_traffic_allowed

    assert global_trip_active() is True
    assert matchbook_traffic_allowed() is False


def test_record_rate_limit_sets_trip(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_RACING_CACHE_DIR", str(tmp_path / "data" / ".cache"))

    from hibs_racing.matchbook_guard import global_trip_active, record_rate_limit

    assert global_trip_active() is False
    record_rate_limit(http_status=429, reason="events")
    assert global_trip_active() is True


def test_poll_interval_throttle(monkeypatch, tmp_path):
    monkeypatch.setenv("HIBS_RACING_CACHE_DIR", str(tmp_path / "data" / ".cache"))
    monkeypatch.setenv("MATCHBOOK_USERNAME", "alice")
    monkeypatch.setenv("MATCHBOOK_PASSWORD", "secret")
    _write_state(tmp_path, {"last_poll_at": datetime.now(timezone.utc).isoformat()})

    from hibs_racing.matchbook_guard import matchbook_traffic_allowed

    assert matchbook_traffic_allowed() is False
    assert matchbook_traffic_allowed(force=True) is True
