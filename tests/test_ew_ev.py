from hibs_racing.place.ew_ev import EachWayQuote, each_way_ev, exchange_place_ev
from hibs_racing.place.exchange_config import exchange_runtime_config


def test_each_way_place_ev_positive_for_consistent_placer():
    ev = each_way_ev(
        model_win_prob=0.08,
        model_place_prob=0.42,
        quote=EachWayQuote(win_decimal=10.0, place_fraction=0.25, places=3),
    )
    assert ev.offered_place_decimal == 3.25
    assert ev.combined_ev > 0


def test_exchange_place_ev_positive_overlay():
    # 50% model vs 2.50 implied ~40% — clear overlay
    ev = exchange_place_ev(0.50, 2.50, commission=0.02)
    assert ev > 0


def test_exchange_place_ev_commission_reduces_edge():
    plain = exchange_place_ev(0.35, 2.20, commission=0.0)
    net = exchange_place_ev(0.35, 2.20, commission=0.05)
    assert net < plain


def test_exchange_place_ev_invalid_odds_is_nan():
    import math

    assert math.isnan(exchange_place_ev(0.3, 1.0))


def test_exchange_runtime_config_env_override(monkeypatch):
    monkeypatch.setenv("HIBS_EXCHANGE_COMMISSION", "0.03")
    monkeypatch.setenv("HIBS_KELLY_FRACTION", "0.20")
    cfg = exchange_runtime_config({})
    assert cfg["exchange_commission"] == 0.03
    assert cfg["kelly_fraction"] == 0.20
    assert cfg["exchange_ev_shadow"] is True
    assert cfg["exchange_ev_production"] is False
