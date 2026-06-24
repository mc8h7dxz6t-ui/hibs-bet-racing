"""ModelGovernor gold-standard tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from inst_spine.errors import IngestValidationError
from inst_spine.product_cli import run_institutional_export, run_institutional_verify
from model_governor.record import record_governance_event


def _snapshot() -> dict:
    return {
        "model_id": "test-model",
        "version": "1.0.0",
        "artifact_hash": "sha256:test",
        "risk_tier": "medium",
        "metrics": {"auc": 0.9},
    }


def test_model_governor_record_and_chain(tmp_path: Path):
    db = tmp_path / "mg.sqlite"
    entry = record_governance_event(
        action="register",
        model_snapshot=_snapshot(),
        outcome={"status": "registered"},
        actor="test-actor",
        database=db,
    )
    assert entry["event_type"] == "model_governance"
    from inst_spine.ledger import AppendOnlyLedger

    assert AppendOnlyLedger(db).verify()["chain_ok"]


def test_model_governor_requires_fields(tmp_path: Path):
    db = tmp_path / "mg.sqlite"
    with pytest.raises(IngestValidationError, match="missing required fields"):
        record_governance_event(
            action="register",
            model_snapshot={"model_id": "x"},
            database=db,
        )


def test_model_governor_invalid_action(tmp_path: Path):
    with pytest.raises(IngestValidationError, match="action must be one of"):
        record_governance_event(action="launch", model_snapshot=_snapshot())


def test_model_governor_cli_export_verify(tmp_path: Path):
    db = tmp_path / "mg.sqlite"
    record_governance_event(
        action="approve",
        model_snapshot=_snapshot(),
        outcome={"status": "approved"},
        database=db,
    )
    tar = tmp_path / "mg_bundle.tar"
    code, body = run_institutional_export(db, product="model-governor", tarball=tar)
    assert code == 0 and body["ok"]
    vcode, vbody = run_institutional_verify(tar, product="model-governor")
    assert vcode == 0 and vbody["ok"]
