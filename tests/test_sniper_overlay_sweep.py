import pandas as pd

from hibs_racing.backtest.gate_benchmark import _apply_gate_flags
from hibs_racing.backtest.snapshot_store import upsert_snapshots
from hibs_racing.backtest.sniper_overlay_sweep import (
    SNIPER_OVERLAY_VARIANTS,
    build_overlay_paper_cfg,
    evaluate_overlay_promotion,
    overlay_variant_ids,
    run_sniper_overlay_sweep,
)
from hibs_racing.features.store import init_db


def _seed_snapshots(db, card_date: str, n_runners: int = 4) -> None:
    rows = []
    for i in range(n_runners):
        rows.append(
            {
                "runner_id": f"{card_date}-r{i}",
                "race_id": f"{card_date}-race",
                "course": "Ascot",
                "race_name": "Class 4 Handicap",
                "field_size": 10,
                "official_rating": 55 + i * 5,
                "win_decimal": 4.0 + i,
                "place_fraction": 0.25,
                "places": 3,
                "model_score": 0.9 - i * 0.05,
                "model_win_prob": 0.2,
                "model_place_prob": 0.40 + i * 0.02,
                "combo_bayes_place": 0.28 + i * 0.02,
                "place_ev": 0.06 + i * 0.02,
                "ew_combined_ev": 0.08 + i * 0.02,
                "flag_raw": 1,
                "trainer_rtf": 10.0 + i * 5,
            }
        )
    frame = pd.DataFrame(rows)
    finish = {r["runner_id"]: 1 if i == 0 else 4 for i, r in enumerate(rows)}
    upsert_snapshots(db, card_date, frame, finish_by_runner=finish)


def test_overlay_variant_count():
    assert len(overlay_variant_ids()) == 8
    assert "gate5_baseline" in SNIPER_OVERLAY_VARIANTS
    assert "sniper_ultra" in SNIPER_OVERLAY_VARIANTS


def test_build_overlay_tighter_than_loose():
    paper = {"min_official_rating": 45, "gate2": {"enabled": True, "max_value_per_race": 3}}
    loose = build_overlay_paper_cfg(paper, SNIPER_OVERLAY_VARIANTS["sniper_loose"])
    ultra = build_overlay_paper_cfg(paper, SNIPER_OVERLAY_VARIANTS["sniper_ultra"])
    assert ultra["min_official_rating"] > loose["min_official_rating"]
    assert ultra["gate2"]["min_confidence"] >= loose["gate2"]["min_confidence"]


def test_sniper_overlay_sweep_walkforward(tmp_path):
    db = tmp_path / "sweep.db"
    init_db(db)
    _seed_snapshots(db, "2026-01-15")
    _seed_snapshots(db, "2026-02-15")

    report = run_sniper_overlay_sweep(
        start="2026-01-01",
        end="2026-02-28",
        database=db,
    )
    assert not report.get("error")
    assert report["overlay_count"] == 8
    assert len(report["ranking"]) == 8
    assert report["best_overlay"] in SNIPER_OVERLAY_VARIANTS
    best = report["overlays"][report["best_overlay"]]
    assert best["aggregate"]["overlay"]["picks"] >= 0


def test_evaluate_overlay_promotion_volume_floor():
    full = {
        "experimental_replay_lanes": {
            "promotion_criteria": {"min_picks_per_month_gate5": 15, "min_aggregate_roi_pct": 10.0},
        }
    }
    promo = evaluate_overlay_promotion(
        overlay_id="test",
        aggregate={
            "overlay": {"picks": 10, "roi_pct": 50.0},
            "gate3": {"picks": 80, "roi_pct": 8.0},
        },
        period_rows=[
            {"overlay": {"picks": 2, "roi_pct": 50.0}, "gate3": {"picks": 10, "roi_pct": 8.0}}
        ]
        * 2,
        months_with_data=2,
        full_cfg=full,
    )
    assert promo["volume_floor_pass"] is False
    assert promo["promotion_ready"] is False
