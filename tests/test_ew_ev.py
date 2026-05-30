from hibs_racing.place.ew_ev import EachWayQuote, each_way_ev


def test_each_way_place_ev_positive_for_consistent_placer():
    # Model thinks place prob high vs book 1/4 terms on 10.0 win
    ev = each_way_ev(
        model_win_prob=0.08,
        model_place_prob=0.42,
        quote=EachWayQuote(win_decimal=10.0, place_fraction=0.25, places=3),
    )
    assert ev.offered_place_decimal == 3.25
    assert ev.combined_ev > 0
