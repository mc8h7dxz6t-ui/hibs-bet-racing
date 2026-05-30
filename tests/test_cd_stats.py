import pandas as pd

from hibs_racing.features.cd_stats import (
    add_all_cd_stats,
    attach_cd_keys,
    distance_bucket,
)
from hibs_racing.features.ranker_matrix import add_within_race_features


def test_distance_bucket_bands():
    assert distance_bucket(5.0) == "sprint"
    assert distance_bucket(6.0) == "sprint"
    assert distance_bucket(7.0) == "mile"
    assert distance_bucket(8.0) == "mile"
    assert distance_bucket(10.0) == "middle"
    assert distance_bucket(12.0) == "middle"
    assert distance_bucket(14.0) == "staying"
    assert distance_bucket(None) == "unknown"


def test_cd_stats_no_leakage():
    frame = pd.DataFrame(
        [
            {
                "race_date": "2024-05-01",
                "race_id": "R1",
                "runner_id": "a",
                "jockey": "J1",
                "trainer": "T1",
                "course": "Chester",
                "distance_f": 7.0,
                "finish_pos": 1,
            },
            {
                "race_date": "2024-05-08",
                "race_id": "R2",
                "runner_id": "b",
                "jockey": "J1",
                "trainer": "T1",
                "course": "Chester",
                "distance_f": 7.0,
                "finish_pos": 3,
            },
            {
                "race_date": "2024-05-15",
                "race_id": "R3",
                "runner_id": "c",
                "jockey": "J1",
                "trainer": "T1",
                "course": "Chester",
                "distance_f": 7.0,
                "finish_pos": 2,
            },
        ]
    )
    out = add_all_cd_stats(frame, alpha=5.0)
    assert out.iloc[0]["jockey_cd_prior_rides"] == 0
    assert out.iloc[1]["jockey_cd_prior_rides"] == 1
    assert out.iloc[1]["jockey_cd_prior_places"] == 1
    assert out.iloc[2]["combo_cd_prior_rides"] == 2
    assert out.iloc[2]["combo_cdd_prior_rides"] == 2


def test_cd_vs_field():
    frame = pd.DataFrame(
        [
            {
                "race_id": "R1",
                "official_rating": 70,
                "rpr": 72,
                "sectional_composite": 0.5,
                "combo_bayes_win": 0.2,
                "jockey_cd_bayes_place": 0.5,
                "trainer_cd_bayes_place": 0.4,
                "combo_cd_bayes_place": 0.45,
                "combo_cdd_bayes_place": 0.42,
            },
            {
                "race_id": "R1",
                "official_rating": 68,
                "rpr": 70,
                "sectional_composite": 0.4,
                "combo_bayes_win": 0.15,
                "jockey_cd_bayes_place": 0.3,
                "trainer_cd_bayes_place": 0.35,
                "combo_cd_bayes_place": 0.32,
                "combo_cdd_bayes_place": 0.30,
            },
        ]
    )
    out = add_within_race_features(frame)
    assert out.iloc[0]["jockey_cd_vs_field"] > 0
    assert out.iloc[1]["jockey_cd_vs_field"] < 0


def test_attach_cd_keys_normalizes_course():
    frame = pd.DataFrame([{"course": "Chester", "distance_f": 6.5, "jockey": "J", "trainer": "T"}])
    out = attach_cd_keys(frame)
    assert out.iloc[0]["course_slug"] == "chester"
    assert out.iloc[0]["dist_bucket"] == "mile"
