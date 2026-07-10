import pandas as pd

from hibs_racing.odds.loader import resolve_scoring_odds


def test_resolve_auto_prefers_embedded(monkeypatch):
    cards = pd.DataFrame([{"runner_id": "r1", "horse_name": "A", "win_decimal": 4.0}])
    odds, meta = resolve_scoring_odds(cards, odds_source="auto")
    assert meta["source"] == "card_embedded"
    assert len(odds) == 1


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
    monkeypatch.setattr("hibs_racing.odds.loader._matchbook_configured", lambda: True)
    monkeypatch.setattr(
        "hibs_racing.odds.loader.matchbook_traffic_allowed",
        lambda force=False: True,
        raising=False,
    )
    monkeypatch.setattr(
        "hibs_racing.matchbook_guard.matchbook_traffic_allowed",
        lambda force=False: True,
    )
    odds, meta = resolve_scoring_odds(cards, odds_source="matchbook")
    assert meta["source"] == "matchbook"
    assert odds.iloc[0]["win_decimal"] == 6.0


def test_resolve_matchbook_falls_back_to_oddschecker(monkeypatch):
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

    def fake_mb(frame, **kwargs):
        return pd.DataFrame(), type("R", (), {"to_dict": lambda self: {"runners_priced": 0}})()

    def fake_oc(frame, **kwargs):
        return (
            pd.DataFrame([{"runner_id": "R1:a", "horse_name": "Horse A", "win_decimal": 5.0}]),
            type("R", (), {"to_dict": lambda self: {"runners_priced": 1}})(),
        )

    monkeypatch.setattr("hibs_racing.odds.loader.fetch_matchbook_odds", fake_mb)
    monkeypatch.setattr("hibs_racing.odds.loader.fetch_oddschecker_odds", fake_oc)
    monkeypatch.setattr("hibs_racing.odds.loader._matchbook_configured", lambda: True)
    monkeypatch.setattr("hibs_racing.matchbook_guard.matchbook_traffic_allowed", lambda force=False: True)

    odds, meta = resolve_scoring_odds(cards, odds_source="matchbook")
    assert meta["source"] == "oddschecker"
    assert odds.iloc[0]["win_decimal"] == 5.0


def test_auto_cascades_when_no_embedded(monkeypatch):
    cards = pd.DataFrame(
        [
            {
                "runner_id": "R1:a",
                "race_id": "R1",
                "card_date": "2026-07-10",
                "horse_name": "Horse A",
            },
            {
                "runner_id": "R1:b",
                "race_id": "R1",
                "card_date": "2026-07-10",
                "horse_name": "Horse B",
            },
        ]
    )

    def fake_mb(frame, **kwargs):
        return (
            pd.DataFrame([{"runner_id": "R1:a", "horse_name": "Horse A", "win_decimal": 3.5}]),
            type("R", (), {"to_dict": lambda self: {"runners_priced": 1}})(),
        )

    monkeypatch.setattr("hibs_racing.odds.loader.fetch_matchbook_odds", fake_mb)
    monkeypatch.setattr("hibs_racing.odds.loader._matchbook_configured", lambda: True)
    monkeypatch.setattr("hibs_racing.matchbook_guard.matchbook_traffic_allowed", lambda force=False: True)
    monkeypatch.setattr("hibs_racing.odds.loader._oddschecker_circuit_open", lambda: True)

    odds, meta = resolve_scoring_odds(cards, odds_source="auto")
    assert "matchbook" in meta.get("layers", [])
    assert len(odds) == 1


def test_oddschecker_skipped_when_circuit_open(monkeypatch):
    cards = pd.DataFrame([{"runner_id": "r1", "horse_name": "A"}])

    def fail_oc(*args, **kwargs):
        raise AssertionError("oddschecker should not be called")

    monkeypatch.setattr("hibs_racing.odds.loader.fetch_oddschecker_odds", fail_oc)
    monkeypatch.setattr("hibs_racing.odds.loader._oddschecker_circuit_open", lambda: True)
    monkeypatch.setattr("hibs_racing.odds.loader._matchbook_configured", lambda: False)

    odds, meta = resolve_scoring_odds(cards, odds_source="oddschecker")
    assert odds is None
    assert "circuit open" in str(meta.get("oddschecker_attempt", {}))
