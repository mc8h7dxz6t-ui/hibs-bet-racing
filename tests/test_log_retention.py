import json
from datetime import datetime, timedelta, timezone

from hibs_racing.features.store import connect, init_db
from hibs_racing.institutional.ledger_events import append_ledger_event
from hibs_racing.institutional.log_retention import (
    brief_ledger_payload,
    run_db_log_retention,
    run_file_log_retention,
    run_log_retention,
)
from hibs_racing.institutional.run_manifest import build_run_manifest, persist_run_manifest


def _iso(days_ago: int) -> str:
    dt = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return dt.replace(microsecond=0).isoformat()


def test_brief_payload_strips_verbose_fields():
    payload = {
        "bet_id": "abc",
        "runner_id": "r1",
        "model_ev": 0.12,
        "timings_ms": {"score_ms": 9999},
        "gates_json": {"foo": "bar"},
    }
    brief = brief_ledger_payload("bet_placed", payload)
    assert brief["_log_tier"] == "brief"
    assert brief["bet_id"] == "abc"
    assert "timings_ms" not in brief
    assert "gates_json" not in brief


def test_db_retention_compacts_and_deletes(tmp_path):
    db = tmp_path / "retention.db"
    init_db(db)

    old_manifest = build_run_manifest(
        run_kind="refresh",
        card_date="2025-01-01",
        runner_count=50,
        value_flag_count=5,
        extras={"timings_ms": {"score_ms": 1200}, "enrich_matched": 40},
    )
    persist_run_manifest(old_manifest, database=db)

    append_ledger_event(
        event_type="bet_placed",
        runner_id="r-old",
        race_id="race-old",
        payload={
            "bet_id": "b1",
            "stake_units": "1.0",
            "offered_win": "5.0",
            "model_ev": "0.08",
            "card_date": "2025-01-01",
        },
        database=db,
    )
    with connect(db) as conn:
        conn.execute(
            "UPDATE ledger_events SET created_at = ? WHERE runner_id = ?",
            (_iso(45), "r-old"),
        )
        conn.execute(
            "UPDATE run_manifests SET created_at = ? WHERE manifest_id = ?",
            (_iso(45), old_manifest.manifest_id),
        )
        conn.commit()

    append_ledger_event(
        event_type="bet_placed",
        runner_id="r-ancient",
        race_id="race-ancient",
        payload={"bet_id": "b2", "stake_units": "1.0"},
        database=db,
    )
    with connect(db) as conn:
        conn.execute(
            "UPDATE ledger_events SET created_at = ? WHERE runner_id = ?",
            (_iso(130), "r-ancient"),
        )
        conn.commit()

    report = run_db_log_retention(database=db, detailed_days=30, brief_days=120, dry_run=False)
    assert report.ledger_compacted == 1
    assert report.ledger_deleted == 1
    assert report.manifests_compacted == 1

    with connect(db) as conn:
        row = conn.execute(
            "SELECT payload_json FROM ledger_events WHERE runner_id = ?",
            ("r-old",),
        ).fetchone()
        payload = json.loads(row[0])
        assert payload["_log_tier"] == "brief"
        assert payload["bet_id"] == "b1"
        assert "model_ev" not in payload

        ancient = conn.execute(
            "SELECT COUNT(*) FROM ledger_events WHERE runner_id = ?",
            ("r-ancient",),
        ).fetchone()[0]
        assert ancient == 0

        extras = conn.execute(
            "SELECT extras_json FROM run_manifests WHERE manifest_id = ?",
            (old_manifest.manifest_id,),
        ).fetchone()[0]
        parsed = json.loads(extras)
        assert parsed["_log_tier"] == "brief"
        assert "timings_ms" not in parsed


def test_file_retention_moves_old_sections_to_brief(tmp_path):
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).strftime("%Y-%m-%dT%H:%M:%SZ")
    new_ts = (datetime.now(timezone.utc) - timedelta(days=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    log_path = log_dir / "daily-refresh-cards.log"
    log_path.write_text(
        f"=== {old_ts} daily-refresh-cards ===\n"
        '{"odds_source": "matchbook", "paper_bets_logged": 12}\n'
        "OK: daily-refresh-cards\n\n"
        f"=== {new_ts} daily-refresh-cards ===\n"
        '{"odds_source": "matchbook", "paper_bets_logged": 8}\n'
        "OK: daily-refresh-cards\n",
        encoding="utf-8",
    )

    report = run_file_log_retention(
        log_dir=log_dir,
        detailed_days=30,
        brief_days=120,
        dry_run=False,
    )
    assert report.file_sections_briefed == 1

    kept = log_path.read_text(encoding="utf-8")
    assert old_ts not in kept
    assert new_ts in kept

    brief = (log_dir / "brief" / "daily-refresh-cards.log").read_text(encoding="utf-8")
    assert "matchbook" in brief
    assert old_ts in brief


def test_run_log_retention_respects_config(tmp_path):
    db = tmp_path / "cfg.db"
    init_db(db)
    report = run_log_retention(database=db, log_dir=tmp_path / "logs", dry_run=True)
    assert report.detailed_days == 30
    assert report.brief_days == 120
