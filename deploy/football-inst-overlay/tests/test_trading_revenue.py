"""trading_revenue — promotion tier and PnL surface."""

from decimal import Decimal

from hibs_predictor.trading_revenue import (
    build_revenue_block,
    infer_phase,
    phase_limits,
    trading_commercial_tier,
)


def test_infer_phase_from_metrics_port():
    assert infer_phase(metrics_url="http://127.0.0.1:9110", env_phase="paper") == "micro"
    assert infer_phase(metrics_url="http://127.0.0.1:9108", env_phase="paper") == "shadow"


def test_phase_limits_micro():
    lim = phase_limits("micro")
    assert lim["max_order_usd"] == 100
    assert lim["max_gross_usd"] == 500


def test_build_revenue_block_unrealized():
    rev = build_revenue_block(
        phase="paper",
        portfolio={
            "available": True,
            "account": {"equity": "10000", "day_pnl": "50", "day_pnl_pct": "0.5", "paper": True},
            "performance": {"equity": "10000", "day_pnl": "50", "day_pnl_pct": "0.5"},
            "equity_positions": [{"unrealized_pl": "10"}, {"unrealized_pl": "-3"}],
            "crypto_positions": [],
        },
    )
    assert rev["position_count"] == 2
    assert Decimal(rev["unrealized_pl_total"]) == Decimal("7")


def test_trading_commercial_tier_design_partner():
    promo = {
        "clean_shadow_days": 10,
        "clean_shadow_days_required": 30,
        "shadow_to_micro": {"passed": False, "critical_pass": False},
        "micro_to_live": {"passed": False},
    }
    tier = trading_commercial_tier(
        phase="paper",
        online=True,
        promotion=promo,
        revenue={"day_pnl_pct": None},
    )
    assert tier["tier"] == "design_partner_evaluation"
    assert tier["score"] >= 55
