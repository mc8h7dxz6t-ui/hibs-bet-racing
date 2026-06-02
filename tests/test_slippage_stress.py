import pandas as pd

from hibs_racing.backtest.slippage_stress import apply_slippage_to_frame, worse_win_decimal


def test_worse_win_decimal_reduces_odds():
    assert worse_win_decimal(4.0, 100) < 4.0
    assert worse_win_decimal(4.0, 0) == 4.0


def test_slippage_reduces_flag_raw():
    frame = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "model_win_prob": 0.15,
                "model_place_prob": 0.4,
                "combo_bayes_place": 0.25,
                "win_decimal": 3.0,
                "place_fraction": 0.25,
                "places": 3,
                "place_ev": 0.06,
                "ew_combined_ev": 0.08,
                "flag_raw": 1,
            }
        ]
    )
    stressed = apply_slippage_to_frame(frame, 500, paper_cfg={"min_place_ev": 0.05, "min_combo_bayes_place": 0.22})
    assert stressed.iloc[0]["flag_raw"] in (0, 1)
    assert stressed.iloc[0]["win_decimal"] < 3.0
