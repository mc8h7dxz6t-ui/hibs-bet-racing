import pandas as pd

from hibs_racing.web_service import _backfill_win_decimal_from_cache


def test_backfill_win_decimal_from_cache(monkeypatch):
    frame = pd.DataFrame(
        [
            {"runner_id": "r1", "horse_name": "A", "win_decimal": None},
            {"runner_id": "r2", "horse_name": "B", "win_decimal": 4.0},
        ]
    )
    cached = pd.DataFrame([{"runner_id": "r1", "win_decimal": 6.5}])

    monkeypatch.setattr(
        "hibs_racing.odds.exchange_quotes.load_cached_exchange_odds",
        lambda cards: cached,
    )
    out = _backfill_win_decimal_from_cache(frame)
    assert float(out.loc[out["runner_id"] == "r1", "win_decimal"].iloc[0]) == 6.5
    assert float(out.loc[out["runner_id"] == "r2", "win_decimal"].iloc[0]) == 4.0
