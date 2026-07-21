"""poll_matchbook_odds_once must not crash when Matchbook returns no quotes."""

from __future__ import annotations

import pandas as pd

from hibs_racing.odds.matchbook import MatchbookFetchReport
from hibs_racing.odds.market_steam import poll_matchbook_odds_once


def test_poll_matchbook_odds_once_empty_quotes_no_keyerror(monkeypatch):
    cards = pd.DataFrame(
        [
            {
                "runner_id": "R1:a",
                "race_id": "R1",
                "card_date": "2026-07-21",
                "off_time": "14:30",
                "course": "Ascot",
                "horse_name": "Horse A",
            }
        ]
    )

    def fake_load():
        return cards

    def fake_fetch(frame, force=False):
        return pd.DataFrame(), MatchbookFetchReport(errors=["matchbook poll gated (rate/owner/trip)"])

    monkeypatch.setattr("hibs_racing.odds.market_steam.load_upcoming_runners", fake_load)
    monkeypatch.setattr("hibs_racing.odds.market_steam.fetch_matchbook_odds", fake_fetch)
    monkeypatch.setattr("hibs_racing.odds.market_steam.filter_pre_race_cards", lambda c: c)

    report = poll_matchbook_odds_once(pre_race_only=False, persist=False)
    assert report.runners_priced == 0
    assert any("gated" in e or "no matchbook" in e for e in report.errors)
