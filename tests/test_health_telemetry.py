"""Health telemetry gold-standard tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from health_telemetry.ingest import ingest_batch


def test_health_telemetry_ingest_and_chain(tmp_path: Path):
    db = tmp_path / "health.sqlite"
    packets = [{"ts": "2026-06-01T12:00:00Z", "hr": 72}, {"ts": "2026-06-01T12:00:01Z", "hr": 73}]
    entry = ingest_batch(device_id="dev-001", packets=packets, database=db)
    assert entry["event_type"] == "telemetry_batch"
    from inst_spine.ledger import AppendOnlyLedger

    assert AppendOnlyLedger(db).verify()["chain_ok"]


def test_health_telemetry_cli_export_verify(tmp_path: Path):
    db = tmp_path / "health.sqlite"
    ingest_batch(
        device_id="dev-cli",
        packets=[{"v": 1}],
        database=db,
    )
    from inst_spine.product_cli import run_institutional_export, run_institutional_verify

    tar = tmp_path / "health_bundle.tar"
    code, body = run_institutional_export(db, product="health-telemetry", tarball=tar)
    assert code == 0 and body["ok"]
    vcode, vbody = run_institutional_verify(tar, product="health-telemetry")
    assert vcode == 0 and vbody["ok"]
