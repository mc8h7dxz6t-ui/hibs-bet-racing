import pandas as pd

from hibs_racing.odds.loader import resolve_scoring_odds


def test_resolve_auto_prefers_embedded(monkeypatch):
    cards = pd.DataFrame([{"horse_name": "A", "win_decimal": 4.0}])
    odds, meta = resolve_scoring_odds(cards, odds_source="auto")
    assert meta["source"] == "card_embedded"


def test_resolve_matchbook_source(monkeypatch):
    cards = pd.DataFrame(
        [
            {
                "runner_id": "R1:a",
                "race_id": "R1",
                "card_date": "2026-05-30",
                "off_time": "14:30",
                "course": "Ascot",
                "horse_name": "Horse A",
            }
        ]
    )

    def fake_fetch(frame, **kwargs):
        return (
            pd.DataFrame([{"horse_name": "Horse A", "win_decimal": 6.0, "best_book": "matchbook"}]),
            type("R", (), {"to_dict": lambda self: {"runners_priced": 1}})(),
        )

    monkeypatch.setattr("hibs_racing.odds.loader.fetch_matchbook_odds", fake_fetch)
    odds, meta = resolve_scoring_odds(cards, odds_source="matchbook")
    assert meta["source"] == "matchbook"
    assert odds.iloc[0]["win_decimal"] == 6.0
