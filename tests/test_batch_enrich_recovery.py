import json

from hibs_racing.ingest.batch_enrich_recovery import (
    checkpoint_path,
    load_checkpoint,
    run_batch_enrich_recovery,
    save_checkpoint,
)


def test_checkpoint_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("HIBS_RACING_DATA_DIR", str(tmp_path / "data"))
    cfg_dir = tmp_path / "ingest"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        """
batch_enrich_recovery:
  checkpoint_file: batch_scrape_checkpoint.txt
paths:
  db_path: data/feature_store.sqlite
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("hibs_racing.config.ROOT", tmp_path)
    save_checkpoint("2025-11-15")
    assert load_checkpoint() == "2025-11-15"
    assert checkpoint_path().exists()


def test_batch_skips_days_without_runners(tmp_path, monkeypatch):
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    monkeypatch.setenv("HIBS_RACING_DATA_DIR", str(tmp_path / "data"))
    cfg_dir = tmp_path / "ingest"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        """
batch_enrich_recovery:
  start: "2025-11-01"
  end: "2025-11-03"
  checkpoint_file: batch_scrape_checkpoint.txt
  progress_file: batch_enrich_recovery_progress.json
paths:
  db_path: data/feature_store.sqlite
rate_limits:
  rp_scrape_day_pause_sec: 0
  rp_racecard_region_pause_sec: 0
""",
        encoding="utf-8",
    )
    monkeypatch.setattr("hibs_racing.config.ROOT", tmp_path)
    from hibs_racing.features.store import connect, init_db

    init_db(db)
    report = run_batch_enrich_recovery(
        start="2025-11-01",
        end="2025-11-03",
        resume=False,
        database=db,
    )
    assert report.days_processed == 3
    assert report.days_fetched == 0
    progress = json.loads((tmp_path / "data" / "batch_enrich_recovery_progress.json").read_text())
    assert progress["days_processed"] == 3
