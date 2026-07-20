from hibs_racing.place.kelly import place_kelly_fraction
from hibs_racing.place.portfolio_kelly import apply_portfolio_place_kelly
import pandas as pd


def test_place_kelly_positive_edge():
    f = place_kelly_fraction(0.50, 2.50, commission=0.02, kelly_fraction=0.25)
    assert f > 0


def test_place_kelly_no_edge_is_zero():
    f = place_kelly_fraction(0.10, 2.0, commission=0.02, kelly_fraction=0.25)
    assert f == 0.0


def test_portfolio_kelly_scales_down_multiple_legs_same_race():
    frame = pd.DataFrame(
        [
            {"race_id": "R1", "model_place_prob": 0.50, "place_decimal": 2.5},
            {"race_id": "R1", "model_place_prob": 0.48, "place_decimal": 2.4},
        ]
    )
    out = apply_portfolio_place_kelly(frame, max_runner_risk_pct=0.10)
    assert out["kelly_place_pct"].iloc[0] > 0
    assert out["kelly_place_pct"].sum() < 20.0
