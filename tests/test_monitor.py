import pandas as pd

from hibs_racing.monitor import top_places_of_day
from hibs_racing.place.paper_ledger import _each_way_pnl


def test_top_places_one_per_race():
    frame = pd.DataFrame(
        [
            {"race_id": "R1", "horse_name": "A", "field_size": 8, "model_place_prob": 0.7, "combo_bayes_place": 0.5},
            {"race_id": "R1", "horse_name": "B", "field_size": 8, "model_place_prob": 0.4, "combo_bayes_place": 0.5},
            {"race_id": "R2", "horse_name": "C", "field_size": 10, "model_place_prob": 0.6, "combo_bayes_place": 0.4},
        ]
    )
    picks = top_places_of_day(frame, top_n=5)
    assert len(picks) == 2
    assert picks[0]["horse_name"] == "A"
    assert picks[0]["day_rank"] == 1


def test_each_way_pnl_placed():
    pnl, status = _each_way_pnl(
        finish_pos=2,
        bet_type="each_way",
        stake=1.0,
        win_decimal=8.0,
        place_fraction=0.25,
        places=3,
    )
    assert status == "placed"
    assert pnl > -1.0
