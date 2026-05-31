import uuid

import pytest

from hibs_racing.features.store import connect, init_db
from hibs_racing.live.execution_log import (
    append_execution_log,
    ensure_execution_log_schema,
    execution_audit_panel,
    execution_log_summary,
    idempotency_key,
    live_execution_exists,
    recent_execution_logs,
)
from hibs_racing.live.execution_router import ExecutionIntent, ExecutionResult, route_execution_batch


@pytest.fixture()
def racing_db(tmp_path):
    db = tmp_path / "exec.sqlite"
    init_db(db)
    ensure_execution_log_schema(db)
    return db


def _intent(**overrides) -> ExecutionIntent:
    base = dict(
        runner_id="r1:h1",
        race_id="r1",
        horse_name="Horse One",
        course="Chester",
        off_time="2:30",
        stake=1.0,
        bet_type="each_way",
        min_odds=5.0,
        offered_odds=5.0,
        value_flag=True,
        kelly_multiplier=1.0,
        steam_gate="proceed",
        matchbook_runner_id=111,
        matchbook_market_id=222,
        matchbook_place_runner_id=112,
        matchbook_place_market_id=223,
        matchbook_event_id=333,
        offered_place_odds=1.8,
        min_place_odds=1.8,
    )
    base.update(overrides)
    return ExecutionIntent(**base)


def _routed_result(intent: ExecutionIntent, *, dry_run: bool = False, bet_leg: str = "win") -> ExecutionResult:
    return ExecutionResult(
        intent=intent,
        venue="matchbook",
        status="routed" if not dry_run else "stub_ok",
        dry_run=dry_run,
        message="ok",
        external_id="offer-1",
        payload={"offer-id": "offer-1", "bet_leg": bet_leg},
    )


def test_execution_log_schema_created(racing_db):
    with connect(racing_db) as conn:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(execution_log)").fetchall()}
    assert "idempotency_key" in cols
    assert "matchbook_place_market_id" in cols
    assert "bet_leg" in cols


def test_idempotency_key_stable():
    assert idempotency_key("r1:h1", "win", "matchbook") == "r1:h1:win:matchbook"


def test_append_and_query_execution_log(racing_db):
    intent = _intent()
    batch_id = str(uuid.uuid4())
    log_id = append_execution_log(_routed_result(intent), batch_id=batch_id, database=racing_db)
    rows = recent_execution_logs(limit=5, batch_id=batch_id, database=racing_db)
    assert len(rows) == 1
    assert rows[0]["log_id"] == log_id
    assert rows[0]["runner_id"] == "r1:h1"
    assert rows[0]["bet_leg"] == "win"
    summary = execution_log_summary(database=racing_db)
    assert summary["total_rows"] == 1
    assert summary["live_routed"] == 1


def test_live_dedup_unique_index(racing_db):
    intent = _intent()
    batch_id = str(uuid.uuid4())
    append_execution_log(_routed_result(intent, dry_run=False, bet_leg="win"), batch_id=batch_id, database=racing_db)
    assert live_execution_exists("r1:h1", "win", "matchbook", database=racing_db)

    with connect(racing_db) as conn:
        with pytest.raises(Exception):
            append_execution_log(_routed_result(intent, dry_run=False, bet_leg="win"), batch_id=batch_id, database=racing_db)


def test_dry_run_allows_repeat_logs(racing_db):
    intent = _intent()
    batch_id = str(uuid.uuid4())
    append_execution_log(_routed_result(intent, dry_run=True), batch_id=batch_id, database=racing_db)
    append_execution_log(_routed_result(intent, dry_run=True), batch_id=batch_id, database=racing_db)
    summary = execution_log_summary(database=racing_db)
    assert summary["total_rows"] == 2
    assert summary["live_routed"] == 0


def test_execution_audit_panel(racing_db):
    intent = _intent()
    batch_id = str(uuid.uuid4())
    append_execution_log(_routed_result(intent, dry_run=True), batch_id=batch_id, database=racing_db)
    panel = execution_audit_panel(database=racing_db)
    assert panel["total_rows"] == 1
    assert panel["status_counts"]["stub_ok"] == 1
    assert len(panel["recent_logs"]) == 1
    assert len(panel["recent_batches"]) == 1
    assert panel["recent_batches"][0]["batch_id"] == batch_id


def test_route_execution_batch_disabled_in_analytics_mode(racing_db):
    report = route_execution_batch([_intent()], database=racing_db, log_results=True)
    assert report["status"] == "disabled"
    assert execution_log_summary(database=racing_db)["total_rows"] == 0
