from hibs_racing.web_service import _ui_data_completeness, novice_pick_candidates


def test_ui_data_completeness_full():
    row = {
        "win_decimal": 5.0,
        "model_win_prob": 0.12,
        "model_place_prob": 0.35,
        "jockey": "A",
        "trainer": "B",
        "card_comment": "ok",
        "official_rating": 90,
    }
    assert _ui_data_completeness(row) == 100


def test_novice_pick_candidates_filters_structure():
    meetings = [
        {
            "course": "York",
            "slug": "1-york",
            "races": [
                {
                    "race_slug": "r1",
                    "off_time": "15:30",
                    "runners": [
                        {
                            "runner_id": "x:1",
                            "horse_name": "Blue Sonic",
                            "win_decimal": 6.0,
                            "model_win_prob": 0.18,
                            "model_place_prob": 0.4,
                            "value_flag": 1,
                            "jockey": "J",
                            "trainer": "T",
                            "card_comment": "well",
                            "official_rating": 80,
                            "market_gauge": {"gate": "proceed", "kelly_multiplier": 1.0},
                        }
                    ],
                }
            ],
        }
    ]
    out = novice_pick_candidates(meetings)
    assert len(out) == 1
    assert out[0]["horse_name"] == "Blue Sonic"
    assert out[0]["value_flag"] is True
    assert out[0]["data_quality_pct"] >= 75
    assert out[0]["steam_gate"] == "proceed"
