from pathlib import Path

import pytest

from hibs_racing.backtest.place_signal import run_place_backtest
from hibs_racing.config import db_path, load_config
from hibs_racing.features.build_features import build_next_run_outcomes, build_tags
from hibs_racing.features.store import init_db
from hibs_racing.ingest.backfill import ingest_csv

FIXTURE = Path(__file__).parent / "fixtures" / "sample_runners.csv"


@pytest.fixture()
def racing_db(tmp_path, monkeypatch):
    db = tmp_path / "test.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    return db


def test_phase_a_pipeline(racing_db):
    n = ingest_csv(FIXTURE, database=racing_db, skip_if_seen=False)
    assert n > 0
    tag_stats = build_tags(database=racing_db)
    assert tag_stats["tagged"] > 0
    outcomes = build_next_run_outcomes(database=racing_db)
    assert outcomes > 0
    report = run_place_backtest(database=racing_db)
    assert report.test_rows >= 0
    assert report.train_rows >= 0
