"""Production scoring guard — no heuristic fallback on VPS."""

from __future__ import annotations

from pathlib import Path

import pytest


def test_production_guard_raises_when_model_missing(tmp_path, monkeypatch):
    from hibs_racing.racing_engine.score_card import apply_scoring_production_guard

    mp = tmp_path / "missing.txt"
    fp = tmp_path / "features.json"
    fp.write_text('["feature_a"]')
    with pytest.raises(FileNotFoundError, match="CRITICAL"):
        apply_scoring_production_guard(model_path=mp, feature_path=fp, scoring_mode="ranker")


def test_production_guard_passes_when_artifacts_present(tmp_path):
    from hibs_racing.racing_engine.score_card import apply_scoring_production_guard

    mp = tmp_path / "lgbm_ranker.txt"
    fp = tmp_path / "lgbm_ranker_features.json"
    mp.write_text("model")
    fp.write_text('["feature_a"]')
    apply_scoring_production_guard(model_path=mp, feature_path=fp, scoring_mode="ranker")
