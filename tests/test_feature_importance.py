import pytest

from hibs_racing.models.feature_importance import (
    build_feature_importance_matrix,
    feature_importance_report,
    format_importance_table,
)


def _lightgbm_works() -> bool:
    try:
        import lightgbm  # noqa: F401
        return True
    except (ImportError, OSError):
        return False


@pytest.mark.skipif(not _lightgbm_works(), reason="lightgbm not installed")
def test_feature_importance_from_trained_model(tmp_path, monkeypatch):
    """Uses real artifacts when present; skips if model missing."""
    from hibs_racing.config import ranker_model_path

    mp = ranker_model_path()
    if not mp.exists():
        pytest.skip("No trained model — run train-ranker first")

    rows = build_feature_importance_matrix()
    assert len(rows) >= 5
    assert rows[0].rank == 1
    assert rows[0].gain >= rows[-1].gain
    table = format_importance_table(rows)
    assert "Feature Importance Matrix" in table
    assert rows[0].feature in table

    report = feature_importance_report(include_holdout=False)
    assert report["top_drivers"]
    assert report["matrix"][0]["gain_pct"] > 0


def test_format_importance_table_empty():
    from hibs_racing.models.feature_importance import FeatureImportanceRow

    rows = [
        FeatureImportanceRow("or_vs_field", 100, 50, 60, 40, 1),
        FeatureImportanceRow("rpr", 50, 30, 30, 20, 2),
    ]
    text = format_importance_table(rows)
    assert "or_vs_field" in text
    assert "rpr" in text
