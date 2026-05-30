import pandas as pd
import pytest

from hibs_racing.odds.matchbook import (
    MatchbookClient,
    _best_back_price,
    _match_event_to_race,
    _select_win_market,
    fetch_matchbook_odds,
)


def test_select_win_market():
    markets = [{"name": "Place", "market-type": "place"}, {"name": "Win", "market-type": "outright"}]
    assert _select_win_market(markets)["name"] == "Win"


def test_best_back_price():
    runner = {
        "prices": [
            {"side": "back", "decimal-odds": 4.2},
            {"side": "back", "decimal-odds": 4.6},
            {"side": "lay", "decimal-odds": 4.8},
        ]
    }
    assert _best_back_price(runner) == 4.6


def test_match_event_to_race():
    event = {
        "start": "2026-06-15T14:30:00.000Z",
        "name": "15:30 Newcastle",
        "meta-tags": [{"type": "VENUE", "name": "Newcastle"}],
    }
    assert _match_event_to_race(event, "Newcastle (AW)", "2026-06-15", "15:30")


class FakeMatchbookClient:
    _sport_id = 24735152712200

    def fetch_horse_events(self, **kwargs):
        return [
            {
                "id": 999,
                "start": "2026-06-15T14:30:00.000Z",
                "name": "15:30 Newcastle",
                "meta-tags": [{"type": "VENUE", "name": "Newcastle"}],
                "markets": [
                    {
                        "name": "Win",
                        "market-type": "outright",
                        "runners": [
                            {
                                "id": 1,
                                "name": "Star Runner",
                                "prices": [{"side": "back", "decimal-odds": 5.0}],
                            },
                            {
                                "id": 2,
                                "name": "Slow Coach",
                                "prices": [{"side": "back", "decimal-odds": 3.2}],
                            },
                        ],
                    }
                ],
            }
        ]


def test_fetch_matchbook_odds_aligns_runners():
    cards = pd.DataFrame(
        [
            {
                "runner_id": "R1:a",
                "race_id": "R1",
                "card_date": "2026-06-15",
                "off_time": "15:30",
                "course": "Newcastle (AW)",
                "horse_name": "Star Runner (GB)",
            },
            {
                "runner_id": "R1:b",
                "race_id": "R1",
                "card_date": "2026-06-15",
                "off_time": "15:30",
                "course": "Newcastle (AW)",
                "horse_name": "Slow Coach",
            },
        ]
    )
    odds, report = fetch_matchbook_odds(cards, client=FakeMatchbookClient())
    assert report.races_matched == 1
    assert report.runners_priced == 2
    assert set(odds["best_book"]) == {"matchbook"}
    assert float(odds.loc[odds["horse_name"].str.contains("Star"), "win_decimal"].iloc[0]) == 5.0


def test_matchbook_login_mock(monkeypatch):
    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"session-token": "tok123"}

    class Sess:
        headers = {}

        def post(self, url, json=None, timeout=30):
            assert json["username"] == "user"
            return Resp()

    client = MatchbookClient(username="user", password="pass", api_base="https://api.test/rest")
    client._session = Sess()
    assert client.login() == "tok123"
