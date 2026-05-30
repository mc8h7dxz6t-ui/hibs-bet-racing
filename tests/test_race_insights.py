import pandas as pd

from hibs_racing.race_insights import build_race_insights


def test_build_race_insights_top_pick():
    frame = pd.DataFrame(
        [
            {
                "horse_name": "Alpha",
                "model_place_prob": 0.55,
                "combo_bayes_place": 0.48,
                "hidden_potential": 12.0,
                "value_flag": 1,
                "field_size": 8,
                "official_rating": 70,
            },
            {
                "horse_name": "Beta",
                "model_place_prob": 0.40,
                "combo_bayes_place": 0.35,
                "hidden_potential": 2.0,
                "value_flag": 0,
                "field_size": 8,
                "official_rating": 75,
            },
        ]
    )
    insights = build_race_insights(frame)
    assert insights["top_pick"]["horse_name"] == "Alpha"
    assert insights["value_count"] == 1
    assert len(insights["bullets"]) >= 1
    assert len(insights["top_picks"]) == 2
