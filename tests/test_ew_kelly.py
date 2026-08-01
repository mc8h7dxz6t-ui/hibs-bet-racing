"""Each-way Kelly — distinct from exchange place Kelly."""

from hibs_racing.place.ew_ev import EachWayQuote
from hibs_racing.place.ew_kelly import each_way_kelly_fraction
from hibs_racing.place.kelly import place_kelly_fraction


def test_each_way_kelly_positive_edge():
    quote = EachWayQuote(win_decimal=8.0, place_fraction=0.25, places=3)
    ew = each_way_kelly_fraction(
        0.18, 0.55, quote, kelly_fraction=0.25, max_runner_risk_pct=0.10
    )
    place = place_kelly_fraction(0.55, 2.2, kelly_fraction=0.25, max_runner_risk_pct=0.10)
    assert ew > 0
    assert place > 0
    assert abs(ew - place) > 1e-6


def test_each_way_kelly_no_edge_is_zero():
    quote = EachWayQuote(win_decimal=3.0, place_fraction=0.25, places=3)
    assert each_way_kelly_fraction(0.05, 0.10, quote) == 0.0


def test_stake_sizing_prefers_ew_kelly():
    from hibs_racing.place.stake_sizing import resolve_stake_units

    row = {"kelly_ew_pct": 3.0, "kelly_place_pct": 1.0}
    assert resolve_stake_units(row, bankroll_units=100.0, bet_type="each_way") == 3.0


def test_stake_sizing_place_uses_place_kelly():
    from hibs_racing.place.stake_sizing import resolve_stake_units

    row = {"kelly_ew_pct": 3.0, "kelly_place_pct": 1.5}
    assert resolve_stake_units(row, bankroll_units=100.0, bet_type="place") == 1.5


def test_portfolio_ew_kelly_scales_same_race():
    import pandas as pd

    from hibs_racing.place.portfolio_kelly import apply_portfolio_ew_kelly

    frame = pd.DataFrame(
        [
            {
                "race_id": "R1",
                "model_win_prob": 0.20,
                "model_place_prob": 0.55,
                "win_decimal": 10.0,
                "place_fraction": 0.25,
                "places": 3,
            },
            {
                "race_id": "R1",
                "model_win_prob": 0.15,
                "model_place_prob": 0.50,
                "win_decimal": 12.0,
                "place_fraction": 0.25,
                "places": 3,
            },
        ]
    )
    out = apply_portfolio_ew_kelly(frame)
    assert out["kelly_ew_pct"].iloc[0] > 0
    assert out["kelly_ew_pct"].sum() < 20.0


def test_phase_4_integration_script_exists():
    from pathlib import Path

    script = Path(__file__).resolve().parents[1] / "scripts/phase_4_integration_test.sh"
    assert script.is_file()
    assert "test_ew_kelly.py" in script.read_text(encoding="utf-8")
