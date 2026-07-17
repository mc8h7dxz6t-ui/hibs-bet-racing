import pandas as pd

from hibs_racing.backtest.gate_config_alignment import (
    ALIGNED_OVERLAY_SPECS,
    BLEND_SPECS,
    INDUSTRY_STANDARD_ANCHORS,
    apply_regime_blend_lane,
    format_gate_matrix_table,
    run_gate_alignment_matrix,
)
from hibs_racing.backtest.snapshot_store import upsert_snapshots
from hibs_racing.features.store import init_db


def _seed(db, card_date: str) -> None:
    rows = []
    for i in range(5):
        rows.append(
            {
                "runner_id": f"{card_date}-r{i}",
                "race_id": f"{card_date}-race",
                "course": "Ascot",
                "race_name": "Class 4 Handicap",
                "field_size": 10,
                "official_rating": 50 + i * 5,
                "win_decimal": 4.0 + i,
                "place_fraction": 0.25,
                "places": 3,
                "model_score": 0.9 - i * 0.05,
                "model_win_prob": 0.2,
                "model_place_prob": 0.42 + i * 0.02,
                "combo_bayes_place": 0.28 + i * 0.02,
                "place_ev": 0.06 + i * 0.02,
                "ew_combined_ev": 0.08 + i * 0.02,
                "flag_raw": 1,
                "trainer_rtf": 10.0 + i * 4,
            }
        )
    frame = pd.DataFrame(rows)
    finish = {r["runner_id"]: 1 if i == 0 else 4 for i, r in enumerate(rows)}
    upsert_snapshots(db, card_date, frame, finish_by_runner=finish)


def test_industry_standards_count():
    assert len(INDUSTRY_STANDARD_ANCHORS) == 3
    assert len(ALIGNED_OVERLAY_SPECS) == 3
    assert len(BLEND_SPECS) == 2


def test_format_gate_matrix_table():
    rows = [
        {
            "lane_id": "gate7",
            "category": "canonical",
            "picks": 100,
            "hit_rate": 0.39,
            "roi_pct": 178.5,
            "pnl_units": 1790.0,
            "delta_vs_gate3_pp": 103.9,
            "volume_floor_pass": True,
            "beats_gate3_roi": True,
        }
    ]
    md = format_gate_matrix_table(rows)
    assert "gate7" in md
    assert "178.5" in md


def test_gate_alignment_matrix(tmp_path):
    db = tmp_path / "align.db"
    init_db(db)
    _seed(db, "2026-01-10")
    _seed(db, "2026-02-10")

    report = run_gate_alignment_matrix(
        start="2026-01-01",
        end="2026-02-28",
        database=db,
    )
    assert not report.get("error")
    assert len(report["matrix"]) == 12
    categories = {r["category"] for r in report["matrix"]}
    assert categories >= {"canonical", "aligned", "blend"}
    assert report.get("best_blend") is not None
    assert "matrix_table_markdown" in report


def test_regime_blend_lane(tmp_path):
    db = tmp_path / "blend.db"
    init_db(db)
    _seed(db, "2026-03-01")
    from hibs_racing.backtest.gate_config_alignment import _prepare_gated_frame
    from hibs_racing.backtest.snapshot_store import load_snapshots, scoring_config_hash
    from hibs_racing.config import load_config

    cfg = load_config()
    paper = cfg.get("paper", {})
    snap = load_snapshots(db, "2026-03-01", "2026-03-01", config_hash=scoring_config_hash(paper))
    gated = _prepare_gated_frame(snap, paper)
    from hibs_racing.backtest.gate_impact import gate7_config

    base = gate7_config(paper, cfg)
    out = apply_regime_blend_lane(
        gated,
        base,
        blend_spec=BLEND_SPECS["blend_gate8_gate7"]["regime_blend"],
        flag_col="flag_test",
        reason_col="test_reason",
    )
    assert "flag_test" in out.columns
