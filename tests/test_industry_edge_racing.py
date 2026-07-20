"""Tests for execution intent ledger and governor wiring."""

from __future__ import annotations

import json
from pathlib import Path


def test_execution_intent_ledger_chain(tmp_path: Path, monkeypatch) -> None:
    from hibs_racing.trading.execution_intent_ledger import append_execution_intent

    ledger = tmp_path / "execution_intent.jsonl"
    monkeypatch.setenv("HIBS_EXEC_INTENT_LEDGER", str(ledger))
    append_execution_intent(verdict={"allowed": True, "status": "PRE_COMMIT_OK"}, source="test")
    append_execution_intent(verdict={"allowed": False, "status": "REJECTED"}, source="test")
    lines = ledger.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 2
    row1 = json.loads(lines[0])
    row2 = json.loads(lines[1])
    assert row1["chain_hash"]
    assert row2["prev_hash"] == row1["chain_hash"]


def test_governor_dispatch_records_intent(tmp_path: Path, monkeypatch) -> None:
    from hibs_racing.features.store import init_db
    from hibs_racing.trading.delta_cache import MarketDeltaCache
    from hibs_racing.trading.execution_governor import ExecutionGovernor, build_order_payload

    db = tmp_path / "feature_store.sqlite"
    ledger = tmp_path / "execution_intent.jsonl"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    monkeypatch.setenv("HIBS_EXEC_INTENT_LEDGER", str(ledger))
    init_db(db)

    gov = ExecutionGovernor(cache=MarketDeltaCache(), database=db)
    payload = build_order_payload(market_id="m1", runner_id="r1", odds=3.0, stake=2.0)
    verdict = gov.dispatch(payload)
    assert verdict.status
    assert ledger.is_file()
    row = json.loads(ledger.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert row["source"] == "execution_governor"
