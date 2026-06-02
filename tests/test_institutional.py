import json

from hibs_racing.features.store import init_db
from hibs_racing.institutional.ledger_events import append_ledger_event
from hibs_racing.institutional.run_manifest import build_run_manifest, persist_run_manifest


def test_run_manifest_roundtrip(tmp_path):
    db = tmp_path / "inst.db"
    init_db(db)
    manifest = build_run_manifest(
        run_kind="test",
        card_date="2026-06-01",
        runner_count=10,
        value_flag_count=2,
    )
    mid = persist_run_manifest(manifest, database=db)
    assert mid == manifest.manifest_id
    assert len(manifest.manifest_hash) == 64


def test_ledger_event_append(tmp_path):
    db = tmp_path / "inst.db"
    init_db(db)
    event = append_ledger_event(
        event_type="test_event",
        payload={"ok": True},
        database=db,
    )
    assert event.event_id
