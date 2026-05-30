import pandas as pd

from hibs_racing.ingest.rp_verdict import extract_rp_verdict, race_verdict_from_runners, _lookup_race_meta


def test_extract_rp_verdict_official():
    text = extract_rp_verdict({"verdict": "Horse X should go close."}, [], {})
    assert text == "Horse X should go close."


def test_extract_rp_verdict_spotlight_fallback():
    runners = [
        {"horseName": "Alpha", "numberOfTips": 5, "spotlight": "Strong form claims."},
        {"horseName": "Beta", "numberOfTips": 1, "spotlight": "Weaker."},
    ]
    text = extract_rp_verdict({}, runners, {})
    assert text == "Alpha — Strong form claims."


def test_extract_rp_verdict_forecast_fallback():
    details = {
        "bettingForecast": [
            {"oddsDesc": "5/2", "horses": [{"horseName": "Ace"}]},
            {"oddsDesc": "3/1", "horses": [{"horseName": "Bolt"}]},
        ]
    }
    text = extract_rp_verdict({}, [], details)
    assert text == "RP forecast: 5/2 Ace; 3/1 Bolt"


def test_race_verdict_from_runners_prefers_rp_verdict():
    frame = pd.DataFrame(
        [
            {"horse_name": "A", "model_place_prob": 0.4, "rp_verdict": "Official RP line.", "card_comment": "x"},
            {"horse_name": "B", "model_place_prob": 0.6, "rp_verdict": "Official RP line.", "card_comment": "y"},
        ]
    )
    assert race_verdict_from_runners(frame) == "Official RP line."


def test_race_verdict_from_runners_comment_fallback():
    frame = pd.DataFrame(
        [
            {"horse_name": "Star", "model_place_prob": 0.55, "card_comment": "Ready to win."},
            {"horse_name": "Other", "model_place_prob": 0.2, "card_comment": "Weaker."},
        ]
    )
    assert race_verdict_from_runners(frame) == "Star — Ready to win."


def test_lookup_race_meta_pm_offset():
    index = {
        ("beverley", 13 * 60 + 45): {"rp_race_id": "123"},
    }
    meta = _lookup_race_meta(index, "Beverley", "1:45")
    assert meta and meta["rp_race_id"] == "123"
