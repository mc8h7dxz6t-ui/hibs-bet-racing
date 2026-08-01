import pandas as pd

from hibs_racing.odds.betfair import (
    BetfairClient,
    _runner_has_odds,
    fetch_betfair_odds,
)
from hibs_racing.odds.course_aliases import COURSE_ALIASES, load_course_aliases_file, merge_course_aliases, venue_matches


def test_venue_matches_betfair_newcastle():
    assert venue_matches("Newcastle (AW)", ["newcastle"])


def test_merge_course_aliases_from_dict():
    before = len(COURSE_ALIASES.get("cartmel", []))
    merge_course_aliases({"cartmel": ["cartmel (uk)", "cartmel"]})
    assert "cartmel" in COURSE_ALIASES
    assert "cartmel (uk)" in COURSE_ALIASES["cartmel"]
    if before == 0:
        del COURSE_ALIASES["cartmel"]


def test_runner_has_odds_filters_non_runner():
    assert not _runner_has_odds({"status": "REMOVED", "prices": [{"side": "back", "decimal-odds": 5.0}]})
    assert not _runner_has_odds({"status": "ACTIVE", "prices": []})
    assert _runner_has_odds(
        {"status": "ACTIVE", "prices": [{"side": "back", "decimal-odds": 4.0, "available-amount": 10}]}
    )


class FakeBetfairClient:
    def list_market_catalogue(self, **kwargs):
        market_types = kwargs.get("market_types") or ["WIN"]
        if "PLACE" in market_types:
            return [
                {
                    "marketId": "1.2002",
                    "marketName": "Place",
                    "event": {
                        "id": "301",
                        "name": "15:30 Newcastle",
                        "venue": "Newcastle",
                        "openDate": "2026-06-15T14:30:00.000Z",
                    },
                    "runners": [
                        {"selectionId": 11, "runnerName": "Star Runner"},
                        {"selectionId": 12, "runnerName": "Slow Coach"},
                        {"selectionId": 13, "runnerName": "Non Runner"},
                    ],
                }
            ]
        return [
            {
                "marketId": "1.2001",
                "marketName": "Win",
                "event": {
                    "id": "301",
                    "name": "15:30 Newcastle",
                    "venue": "Newcastle",
                    "openDate": "2026-06-15T14:30:00.000Z",
                },
                "runners": [
                    {"selectionId": 11, "runnerName": "Star Runner"},
                    {"selectionId": 12, "runnerName": "Slow Coach"},
                    {"selectionId": 13, "runnerName": "Non Runner"},
                ],
            }
        ]

    def list_market_book(self, market_ids):
        books = []
        for mid in market_ids:
            if str(mid).endswith("2001"):
                books.append(
                    {
                        "marketId": mid,
                        "runners": [
                            {
                                "selectionId": 11,
                                "status": "ACTIVE",
                                "ex": {"availableToBack": [{"price": 5.0, "size": 50}]},
                            },
                            {
                                "selectionId": 12,
                                "status": "ACTIVE",
                                "ex": {"availableToBack": [{"price": 3.2, "size": 40}]},
                            },
                            {"selectionId": 13, "status": "REMOVED", "ex": {}},
                        ],
                    }
                )
            else:
                books.append(
                    {
                        "marketId": mid,
                        "runners": [
                            {
                                "selectionId": 11,
                                "status": "ACTIVE",
                                "ex": {"availableToBack": [{"price": 1.9, "size": 30}]},
                            },
                            {
                                "selectionId": 12,
                                "status": "ACTIVE",
                                "ex": {"availableToBack": [{"price": 1.5, "size": 20}]},
                            },
                        ],
                    }
                )
        return books

    def close(self):
        return None


def test_fetch_betfair_odds_aligns_runners_and_skips_non_runners():
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
            {
                "runner_id": "R1:c",
                "race_id": "R1",
                "card_date": "2026-06-15",
                "off_time": "15:30",
                "course": "Newcastle (AW)",
                "horse_name": "Non Runner",
            },
        ]
    )
    odds, report = fetch_betfair_odds(cards, client=FakeBetfairClient())
    assert report.races_matched == 1
    assert report.runners_priced == 2
    assert report.runners_skipped_no_odds == 1
    assert set(odds["best_book"]) == {"betfair"}
    assert float(odds.loc[odds["horse_name"].str.contains("Star"), "win_decimal"].iloc[0]) == 5.0
    star = odds.loc[odds["horse_name"].str.contains("Star")].iloc[0]
    assert int(star["betfair_selection_id"]) == 11
    assert str(star["betfair_market_id"]).endswith("2001")


def test_betfair_login_mock(monkeypatch):
    class Resp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "SUCCESS", "token": "tok-bf"}

    class Sess:
        headers = {}

        def post(self, url, data=None, headers=None, timeout=30):
            assert data["username"] == "user"
            return Resp()

    client = BetfairClient(app_key="key", username="user", password="pass")
    client._session = Sess()
    assert client.login() == "tok-bf"
    assert client._session.headers["X-Authentication"] == "tok-bf"


def test_load_course_aliases_file_yaml(tmp_path):
    path = tmp_path / "aliases.yaml"
    path.write_text("cartmel:\n  - cartmel festival\n", encoding="utf-8")
    load_course_aliases_file(path)
    assert "cartmel festival" in COURSE_ALIASES.get("cartmel", [])
