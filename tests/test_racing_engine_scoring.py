import pandas as pd
import pytest

from hibs_racing.racing_engine.score_card import (
    apply_scoring,
    apply_scoring_production_guard,
    attach_win_probs,
    run_legacy_heuristic,
)


def _sample_race_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "race_id": "R1",
                "combo_bayes_place": 0.5,
                "sectional_composite": 0.4,
                "hidden_potential": 5.0,
                "finishing_burst_level": 1,
                "or_vs_field": 2.0,
                "combo_vs_field": 0.1,
            },
            {
                "race_id": "R1",
                "combo_bayes_place": 0.3,
                "sectional_composite": 0.2,
                "hidden_potential": 1.0,
                "finishing_burst_level": 0,
                "or_vs_field": -1.0,
                "combo_vs_field": -0.05,
            },
        ]
    )


def test_run_legacy_heuristic_sets_method_and_probs():
    out = run_legacy_heuristic(_sample_race_df(), reason="test")
    assert (out["scoring_method"] == "heuristic").all()
    assert out.iloc[0]["scoring_fallback_reason"] == "test"
    assert abs(out["model_win_prob"].sum() - 1.0) < 1e-6
    assert out.iloc[0]["model_win_prob"] > out.iloc[1]["model_win_prob"]


def test_apply_scoring_missing_artifacts(tmp_path, monkeypatch):
    monkeypatch.setattr("hibs_racing.config.ROOT", tmp_path)
    cfg_dir = tmp_path / "ingest"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        """
paths:
  model_dir: data/models
ranker:
  scoring_mode: auto
  model_file: missing.txt
  feature_file: missing.json
""",
        encoding="utf-8",
    )
    from hibs_racing.config import load_config

    out = apply_scoring(_sample_race_df(), config_path=cfg_dir / "config.yaml")
    assert out.iloc[0]["scoring_method"] == "heuristic"
    assert "missing" in out.iloc[0]["scoring_fallback_reason"].lower()


def test_production_guard_raises_when_missing(tmp_path):
    mp = tmp_path / "missing.txt"
    fp = tmp_path / "missing.json"
    with pytest.raises(FileNotFoundError, match="CRITICAL"):
        apply_scoring_production_guard(model_path=mp, feature_path=fp, scoring_mode="ranker")


def test_attach_win_probs_numerical_stability():
    frame = pd.DataFrame({"race_id": ["R1", "R1", "R1"], "model_raw_score": [1000.0, 999.0, 998.0]})
    out = attach_win_probs(frame)
    assert out["model_win_prob"].between(0, 1).all()
    assert abs(out["model_win_prob"].sum() - 1.0) < 1e-6
