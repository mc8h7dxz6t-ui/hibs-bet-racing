"""Fixed ρ match-style restriction until per-league MLE."""

from __future__ import annotations

import pytest


def test_clamp_rho_bounds():
    from hibs_predictor.historic_calibration import _clamp_rho

    assert _clamp_rho(-0.5) == -0.25
    assert _clamp_rho(0.2) == 0.05
    assert _clamp_rho(-0.10) == -0.10


def test_fixed_rho_scaled_on_heavy_mismatch(monkeypatch):
    from hibs_predictor.historic_calibration import resolve_dixon_coles_rho

    monkeypatch.delenv("HIBS_CALIBRATION_CACHE", raising=False)
    monkeypatch.setenv("HIBS_DIXON_COLES_RHO", "-0.12")
    monkeypatch.setenv("HIBS_DIXON_COLES_RHO_MATCH_STYLE", "1")

    typical_rho, typical_dbg = resolve_dixon_coles_rho("EPL", xg_home=1.35, xg_away=1.15)
    mismatch_rho, mismatch_dbg = resolve_dixon_coles_rho("EPL", xg_home=2.2, xg_away=0.55)

    assert typical_dbg["source"] == "env_default"
    assert typical_dbg["match_style_scale"] == 1.0
    assert typical_rho == pytest.approx(-0.12)
    assert abs(mismatch_rho) < abs(typical_rho)
    assert mismatch_dbg["restriction"] == "fixed_rho_match_style_until_mle"


def test_cached_league_rho_not_scaled(monkeypatch, tmp_path):
    from hibs_predictor.historic_calibration import resolve_dixon_coles_rho

    cache = tmp_path / "calibration_v1.json"
    cache.write_text(
        '{"leagues":{"EPL":{"rho":-0.14,"n":40}}}',
        encoding="utf-8",
    )
    monkeypatch.setenv("HIBS_CALIBRATION_CACHE", str(cache))
    monkeypatch.setenv("HIBS_DIXON_COLES_RHO", "-0.10")

    rho, dbg = resolve_dixon_coles_rho("EPL", xg_home=2.4, xg_away=0.5)
    assert dbg["source"] == "cache"
    assert rho == pytest.approx(-0.14)
    assert dbg["match_style_scale"] == 1.0


def test_match_style_restriction_can_be_disabled(monkeypatch):
    from hibs_predictor.historic_calibration import resolve_dixon_coles_rho

    monkeypatch.setenv("HIBS_DIXON_COLES_RHO", "-0.12")
    monkeypatch.setenv("HIBS_DIXON_COLES_RHO_MATCH_STYLE", "0")

    rho, dbg = resolve_dixon_coles_rho("EPL", xg_home=2.2, xg_away=0.55)
    assert rho == pytest.approx(-0.12)
    assert dbg["restriction"] == "match_style_disabled"


def test_extreme_mismatch_draw_less_distorted_than_full_rho(monkeypatch):
    from hibs_predictor.betting_engine import BettingEngine

    monkeypatch.setenv("HIBS_DIXON_COLES_RHO", "-0.15")
    monkeypatch.setenv("HIBS_DIXON_COLES_RHO_MATCH_STYLE", "1")
    engine = BettingEngine({})

    restricted = engine._poisson_match_probs(2.2, 0.55, league_code="EPL")
    monkeypatch.setenv("HIBS_DIXON_COLES_RHO_MATCH_STYLE", "0")
    unrestricted = engine._poisson_match_probs(2.2, 0.55, league_code="EPL")

    assert restricted["draw"] < unrestricted["draw"]
