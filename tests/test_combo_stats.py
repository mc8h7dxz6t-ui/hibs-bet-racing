import pandas as pd

from hibs_racing.features.combo_stats import add_point_in_time_combo_stats, bayesian_rate


def test_bayesian_rate_smoothing():
    wins = pd.Series([0, 1, 0])
    rides = pd.Series([0, 1, 10])
    rate = bayesian_rate(wins, rides, global_rate=0.1, alpha=8.0)
    assert abs(rate.iloc[0] - 0.1) < 0.01
    assert rate.iloc[1] > rate.iloc[0]


def test_combo_stats_no_leakage():
    frame = pd.DataFrame(
        [
            {"race_date": "2024-05-01", "race_id": "R1", "runner_id": "a", "jockey": "J1", "trainer": "T1", "finish_pos": 1},
            {"race_date": "2024-05-08", "race_id": "R2", "runner_id": "b", "jockey": "J1", "trainer": "T1", "finish_pos": 3},
        ]
    )
    out = add_point_in_time_combo_stats(frame, alpha=5.0)
    first = out.iloc[0]
    second = out.iloc[1]
    assert first["combo_prior_rides"] == 0
    assert second["combo_prior_rides"] == 1
    assert second["combo_prior_wins"] == 1
