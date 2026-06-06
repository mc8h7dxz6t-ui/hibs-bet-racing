from hibs_racing.backtest.snapshot_store import resolve_snapshot_config_hash, scoring_config_hash
from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db


def test_resolve_best_matches_largest_snapshot_hash():
    cfg = load_config()
    db = db_path(cfg)
    init_db(db)
    with connect(db) as conn:
        row = conn.execute(
            """
            SELECT config_hash FROM scored_runner_snapshots
            GROUP BY config_hash ORDER BY COUNT(*) DESC LIMIT 1
            """
        ).fetchone()
    if not row:
        return
    expected = str(row[0])
    assert resolve_snapshot_config_hash(db, cfg.get("paper", {}), explicit="best") == expected


def test_resolve_prefix_matches_full_hash():
    cfg = load_config()
    db = db_path(cfg)
    init_db(db)
    with connect(db) as conn:
        row = conn.execute(
            "SELECT config_hash FROM scored_runner_snapshots LIMIT 1"
        ).fetchone()
    if not row:
        return
    full = str(row[0])
    assert resolve_snapshot_config_hash(db, explicit=full[:8]) == full


def test_resolve_default_is_live_hash():
    cfg = load_config()
    db = db_path(cfg)
    paper = cfg.get("paper", {})
    assert resolve_snapshot_config_hash(db, paper) == scoring_config_hash(paper)
