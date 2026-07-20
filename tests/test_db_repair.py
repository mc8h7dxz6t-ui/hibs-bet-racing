"""Tests for feature_store SQLite repair and health value-lane fields."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from unittest.mock import patch

import pytest


def test_integrity_check_missing(tmp_path: Path) -> None:
    from hibs_racing.features.db_repair import integrity_check

    db = tmp_path / "missing.sqlite"
    report = integrity_check(db)
    assert report["ok"] is False
    assert report["error"] == "missing"


def test_integrity_check_ok(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hibs_racing.features.db_repair import integrity_check
    from hibs_racing.features.store import init_db

    db = tmp_path / "feature_store.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    report = integrity_check(db)
    assert report["ok"] is True


def test_integrity_check_malformed(tmp_path: Path) -> None:
    from hibs_racing.features.db_repair import integrity_check

    db = tmp_path / "feature_store.sqlite"
    db.write_bytes(b"not a sqlite database\x00\xff")
    report = integrity_check(db)
    assert report["ok"] is False


def test_repair_feature_store_reinit_from_corrupt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hibs_racing.features.db_repair import integrity_check, repair_feature_store

    db = tmp_path / "feature_store.sqlite"
    db.write_bytes(b"corrupt sqlite image")
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))

    report = repair_feature_store(db)
    assert report["ok"] is True
    assert report["action"] in ("reinitialized_empty", "restored_backup", "sqlite_recover")
    assert integrity_check(db)["ok"] is True


def test_repair_feature_store_restores_backup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from hibs_racing.features.db_repair import integrity_check, repair_feature_store
    from hibs_racing.features.store import init_db

    good = tmp_path / "feature_store.sqlite.bak"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(tmp_path / "feature_store.sqlite"))
    init_db(good)

    corrupt = tmp_path / "feature_store.sqlite"
    corrupt.write_bytes(b"corrupt")

    report = repair_feature_store(corrupt)
    assert report["ok"] is True
    assert report["action"] == "restored_backup"
    assert integrity_check(corrupt)["ok"] is True


def test_value_lane_blockers() -> None:
    from hibs_racing.features.db_repair import value_lane_blockers

    blockers = value_lane_blockers(
        {
            "db_ok": True,
            "db_integrity_ok": True,
            "card_fresh": True,
            "unscored_runners": 3,
            "nan_integrity_passed": False,
            "runners_loaded": 10,
        }
    )
    assert "unscored_runners=3" in blockers
    assert "nan_integrity_failed" in blockers
    assert "db_integrity_failed" not in blockers


def test_health_includes_value_lane_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    from hibs_racing.web_service import health_status

    monkeypatch.setenv("HIBS_HEALTH_LIGHT", "1")
    with patch("hibs_racing.features.db_repair.integrity_check", return_value={"ok": True}), patch(
        "hibs_racing.web_service.load_upcoming_runners",
        return_value=__import__("pandas").DataFrame(),
    ), patch("hibs_racing.web_service.init_db"), patch(
        "hibs_racing.web_service.connect"
    ) as mock_connect:
        conn = sqlite3.connect(":memory:")
        mock_connect.return_value.__enter__.return_value = conn
        conn.execute("CREATE TABLE card_scores (runner_id TEXT)")
        payload = health_status().to_dict()

    assert "matchbook_note" in payload
    assert "value_lane_blockers" in payload
    assert "value_lane_ready" in payload
    assert "matchbook=false" in payload["matchbook_note"]


def test_configure_connection_malformed_hint(tmp_path: Path) -> None:
    from hibs_racing.features.store import _configure_connection

    db = tmp_path / "bad.sqlite"
    db.write_bytes(b"bad")
    conn = sqlite3.connect(str(db))
    with pytest.raises(sqlite3.DatabaseError, match="repair-feature-store"):
        _configure_connection(conn)
