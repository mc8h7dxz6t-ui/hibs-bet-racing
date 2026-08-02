"""Card store upsert (no full-table DELETE) + quant horse tracker sync."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from hibs_racing.cards.store import load_upcoming_runners, store_upcoming_runners
from hibs_racing.features.store import connect, init_db
from hibs_racing.quant.horse_tracker_sync import sync_card_horses_to_quant_plane


def _minimal_runner_frame(runner_id: str, card_date: str, horse_id: str) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "runner_id": runner_id,
                "race_id": f"race-{runner_id}",
                "card_date": card_date,
                "horse_id": horse_id,
                "horse_name": f"Horse {horse_id}",
                "course": "Test Course",
                "off_time": "14:00",
                "race_natural_key": f"nk-{runner_id}",
            }
        ]
    )


def test_store_upcoming_runners_upsert_preserves_other_card_dates(tmp_path):
    db = tmp_path / "feature_store.sqlite"
    frame_a = _minimal_runner_frame("r1", "2026-08-03", "h1")
    frame_b = _minimal_runner_frame("r2", "2026-08-04", "h2")

    store_upcoming_runners(frame_a, source="test", database=db)
    store_upcoming_runners(frame_b, source="test", database=db)

    active = load_upcoming_runners(database=db)
    assert len(active) == 2
    ids = set(active["runner_id"].astype(str))
    assert ids == {"r1", "r2"}


def test_store_marks_withdrawn_not_delete(tmp_path):
    db = tmp_path / "feature_store.sqlite"
    frame = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "race_id": "race-1",
                "card_date": "2026-08-03",
                "horse_id": "h1",
                "horse_name": "Alpha",
                "course": "A",
                "off_time": "14:00",
                "race_natural_key": "nk-1",
            },
            {
                "runner_id": "r2",
                "race_id": "race-1",
                "card_date": "2026-08-03",
                "horse_id": "h2",
                "horse_name": "Beta",
                "course": "A",
                "off_time": "14:00",
                "race_natural_key": "nk-1",
            },
        ]
    )
    store_upcoming_runners(frame, source="test", database=db)

    frame_one = frame.iloc[[0]].copy()
    store_upcoming_runners(frame_one, source="test", database=db)

    all_rows = load_upcoming_runners(database=db, include_withdrawn=True)
    withdrawn = all_rows[all_rows["runner_id"] == "r2"].iloc[0]
    assert str(withdrawn.get("runner_status") or "") == "withdrawn"

    active = load_upcoming_runners(database=db)
    assert list(active["runner_id"]) == ["r1"]


def test_sync_card_horses_to_quant_plane(tmp_path, monkeypatch):
    quant_db = tmp_path / "quant_platform.sqlite"
    monkeypatch.setenv("QUANT_DATA_PLANE_DB", str(quant_db))
    monkeypatch.setenv("QUANT_HORSE_TRACKER_SYNC", "1")

    frame = _minimal_runner_frame("r9", "2026-08-05", "h9")
    result = sync_card_horses_to_quant_plane(frame)
    assert result["ok"]
    assert result["horses_upserted"] == 1
    assert result["tracker_runs_upserted"] == 1

    init_db(quant_db)
    with connect(quant_db) as conn:
        n_horses = conn.execute("SELECT COUNT(*) FROM horse_registry").fetchone()[0]
        n_runs = conn.execute("SELECT COUNT(*) FROM horse_tracker").fetchone()[0]
    assert n_horses == 1
    assert n_runs == 1
