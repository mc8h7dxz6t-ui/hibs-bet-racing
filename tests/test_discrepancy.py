import pandas as pd

from hibs_racing.features.discrepancy import hidden_potential_score


def test_hidden_potential_high_pace_low_or():
    row = pd.Series(
        {
            "official_rating": 55,
            "finishing_burst_level": 3,
            "sectional_composite": 0.9,
            "race_class": "Class 6",
            "horse_avg_class": 5.0,
        }
    )
    score = hidden_potential_score(row)
    low_or_row = row.copy()
    low_or_row["official_rating"] = 80
    assert score > hidden_potential_score(low_or_row)
