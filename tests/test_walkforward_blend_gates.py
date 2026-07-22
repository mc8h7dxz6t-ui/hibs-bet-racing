import pandas as pd

from hibs_racing.backtest.gate_impact import run_gate_lane_walkforward
from hibs_racing.backtest.snapshot_store import upsert_snapshots
from hibs_racing.features.store import init_db


def _seed_month(db, card_date: str) -> None:
    rows = []
    for race_idx in range(2):
        race_id = f"{card_date}-race{race_idx}"
        for runner_idx in range(6):
            rows.append(
                {
                    "runner_id": f"{card_date}-r{race_idx}-{runner_idx}",
                    "race_id": race_id,
                    "course": "Ascot",
                    "race_name": "Class 4 Handicap",
                    "field_size": 10,
                    "official_rating": 50 + runner_idx * 5,
                    "win_decimal": 3.0 + runner_idx * 1.2,
                    "place_fraction": 0.25,
                    "places": 3,
                    "model_score": 0.9 - runner_idx * 0.03,
                    "model_win_prob": 0.2,
                    "model_place_prob": 0.35,
                    "combo_bayes_place": 0.28,
                    "place_ev": 0.08,
                    "ew_combined_ev": 0.1,
                    "flag_raw": 1,
                    "trainer_rtf": 12.0 + runner_idx * 3,
                }
            )
    frame = pd.DataFrame(rows)
    finish = {r["runner_id"]: 1 if i % 4 == 0 else 5 for i, r in enumerate(rows)}
    upsert_snapshots(db, card_date, frame, finish_by_runner=finish)


def test_walkforward_aggregate_includes_blend_gates(tmp_path):
    db = tmp_path / "wf.db"
    init_db(db)
    _seed_month(db, "2026-01-10")
    _seed_month(db, "2026-02-10")

    report = run_gate_lane_walkforward(
        start="2026-01-01",
        end="2026-02-28",
        database=db,
    )
    assert not report.get("error")
    agg = report["aggregate"]
    for lane in ("gate8", "gate9", "gate10", "gate11"):
        assert lane in agg, f"missing {lane} in walkforward aggregate"
