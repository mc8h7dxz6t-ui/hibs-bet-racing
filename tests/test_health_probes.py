"""Shared readiness probe helpers."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path


def test_sqlite_db_ready_creates_parent(tmp_path):
    from inst_spine.health_probes import sqlite_db_ready

    db = tmp_path / "nested" / "probe.sqlite"
    ok, detail = sqlite_db_ready(db)
    assert ok is True
    assert "sqlite_ok" in detail


def test_readiness_payload_all_ok():
    from inst_spine.health_probes import readiness_payload

    body = readiness_payload(
        product="test",
        checks={"a": (True, "ok"), "b": (True, "ok")},
    )
    assert body["ready"] is True
    assert body["ok"] is True


def test_readiness_payload_partial_fail():
    from inst_spine.health_probes import readiness_payload

    body = readiness_payload(
        product="test",
        checks={"a": (True, "ok"), "b": (False, "down")},
    )
    assert body["ready"] is False
