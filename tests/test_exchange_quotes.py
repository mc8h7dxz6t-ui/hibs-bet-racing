import pandas as pd

from hibs_racing.odds.exchange_quotes import (
    exchange_spread_bps,
    persist_exchange_quotes,
    slippage_bps,
)
from hibs_racing.odds.matchbook import _top_of_book
from hibs_racing.features.store import connect, init_db


def test_exchange_spread_bps():
    assert exchange_spread_bps(4.0, 4.2) == 487.8
    assert exchange_spread_bps(4.0, None) is None
    assert exchange_spread_bps(4.2, 4.0) is None


def test_slippage_bps_shortening_hurts_backer():
    # Offered 5.0, SP 4.5 → positive slippage bps (worse for backer)
    assert slippage_bps(5.0, 4.5) == 1111.11


def test_top_of_book_back_and_lay():
    runner = {
        "prices": [
            {"side": "back", "decimal-odds": 4.2, "available-amount": 120.0},
            {"side": "back", "decimal-odds": 4.6, "available-amount": 80.0},
            {"side": "lay", "decimal-odds": 4.8, "available-amount": 50.0},
            {"side": "lay", "decimal-odds": 5.0, "available-amount": 200.0},
        ]
    }
    back, back_liq = _top_of_book(runner, "back")
    lay, lay_liq = _top_of_book(runner, "lay")
    assert back == 4.6
    assert back_liq == 80.0
    assert lay == 4.8
    assert lay_liq == 50.0


def test_persist_exchange_quotes(tmp_path):
    db = tmp_path / "test.sqlite"
    init_db(db)
    odds = pd.DataFrame(
        [
            {
                "runner_id": "r1",
                "card_date": "2026-06-01",
                "race_id": "race1",
                "win_decimal": 5.0,
                "back_price": 5.0,
                "back_liquidity": 100.0,
                "lay_price": 5.2,
                "lay_liquidity": 40.0,
                "exchange_spread_bps": exchange_spread_bps(5.0, 5.2),
                "odds_source": "matchbook",
            }
        ]
    )
    out = persist_exchange_quotes(odds, poll_milestone="baseline", database=db)
    assert out["rows"] == 1
    with connect(db) as conn:
        row = conn.execute(
            "SELECT back_price, lay_price, poll_milestone FROM exchange_quotes WHERE runner_id = 'r1'"
        ).fetchone()
    assert row[0] == 5.0
    assert row[1] == 5.2
    assert row[2] == "baseline"
