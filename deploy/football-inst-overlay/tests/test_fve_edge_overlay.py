"""FVE lines proxy edge overlay fields."""

from __future__ import annotations

from hibs_predictor.fve_lines_proxy import _edge_bps_overlay, _fixture_packet


def test_fixture_packet_includes_model_and_edge():
    row = {
        "home_team": "Arsenal",
        "away_team": "Chelsea",
        "best_odds_1x2": {"home": 2.1, "draw": 3.4, "away": 3.5},
        "prediction": {"probabilities": {"home": 0.52, "draw": 0.24, "away": 0.24}},
    }
    pkt = _fixture_packet(row)
    assert pkt["model_probabilities_1x2"]["home"] == 0.52
    assert pkt["hibs_edge_bps"]["home"] is not None


def test_edge_bps_positive_when_model_beats_market():
    edge = _edge_bps_overlay({"home": 0.55}, {"home": 2.2})
    assert edge["home"] is not None
    assert edge["home"] > 0
