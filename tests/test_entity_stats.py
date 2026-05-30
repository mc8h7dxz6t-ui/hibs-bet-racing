import pandas as pd

from hibs_racing.features.entity_stats import (
    add_all_entity_stats,
    add_point_in_time_entity_stats,
)


def test_jockey_stats_no_leakage():
    frame = pd.DataFrame(
        [
            {"race_date": "2024-05-01", "race_id": "R1", "runner_id": "a", "jockey": "J1", "trainer": "T1", "finish_pos": 1},
            {"race_date": "2024-05-08", "race_id": "R2", "runner_id": "b", "jockey": "J1", "trainer": "T2", "finish_pos": 3},
            {"race_date": "2024-05-15", "race_id": "R3", "runner_id": "c", "jockey": "J1", "trainer": "T1", "finish_pos": 2},
        ]
    )
    out = add_point_in_time_entity_stats(frame, entity_col="jockey", prefix="jockey", alpha=5.0)
    assert out.iloc[0]["jockey_prior_rides"] == 0
    assert out.iloc[1]["jockey_prior_rides"] == 1
    assert out.iloc[1]["jockey_prior_wins"] == 1
    assert out.iloc[2]["jockey_prior_places"] == 2


def test_trainer_rolling_90d():
    rows = []
    for i in range(5):
        rows.append(
            {
                "race_date": f"2024-06-{1 + i * 7:02d}",
                "race_id": f"R{i}",
                "runner_id": f"x{i}",
                "jockey": "J",
                "trainer": "T",
                "finish_pos": 1 if i % 2 == 0 else 4,
            }
        )
    out = add_all_entity_stats(pd.DataFrame(rows), alpha=5.0)
    last = out.iloc[-1]
    assert last["trainer_prior_rides"] == 4
    assert 0 <= last["trainer_place_90d"] <= 1
    assert 0 <= last["trainer_consistency"] <= 1


def test_entity_vs_field_in_matrix():
    from hibs_racing.features.ranker_matrix import add_within_race_features

    frame = pd.DataFrame(
        [
            {
                "race_id": "R1",
                "official_rating": 70,
                "rpr": 72,
                "sectional_composite": 0.5,
                "combo_bayes_win": 0.2,
                "jockey_bayes_place": 0.5,
                "trainer_bayes_place": 0.4,
            },
            {
                "race_id": "R1",
                "official_rating": 68,
                "rpr": 70,
                "sectional_composite": 0.4,
                "combo_bayes_win": 0.15,
                "jockey_bayes_place": 0.3,
                "trainer_bayes_place": 0.35,
            },
        ]
    )
    out = add_within_race_features(frame)
    assert out.iloc[0]["jockey_vs_field"] > 0
    assert out.iloc[1]["jockey_vs_field"] < 0
