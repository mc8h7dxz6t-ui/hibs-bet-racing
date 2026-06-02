import pandas as pd

from hibs_racing.backtest.gate2_sensitivity import run_gate2_cap_sensitivity
from hibs_racing.backtest.snapshot_store import upsert_snapshots
from hibs_racing.features.store import init_db


def test_gate2_cap_sensitivity_runs_on_snapshots(tmp_path):
    db = tmp_path / "g2.db"
    init_db(db)
    rows = []
    for i in range(12):
        rows.append(
            {
                "runner_id": f"r{i}",
                "race_id": "race1" if i < 6 else "race2",
                "course": "Ascot",
                "race_name": "Handicap",
                "field_size": 12,
                "official_rating": 80,
                "win_decimal": 5.0,
                "place_fraction": 0.25,
                "places": 3,
                "model_score": 1.0 - i * 0.02,
                "model_win_prob": 0.12,
                "model_place_prob": 0.4,
                "combo_bayes_place": 0.3,
                "place_ev": 0.1,
                "ew_combined_ev": 0.12,
                "flag_raw": 1,
            }
        )
    frame = pd.DataFrame(rows)
    upsert_snapshots(db, "2026-05-10", frame)

    report = run_gate2_cap_sensitivity(
        start="2026-05-10",
        end="2026-05-10",
        database=db,
        use_snapshots=True,
    )
    assert report.start == "2026-05-10"
    assert "with_caps" in report.to_dict()
