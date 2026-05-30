from hibs_racing.models.feature_impact import (
    FEATURE_GROUPS,
    export_feature_impact_artifacts,
    load_feature_impact_report,
    render_importance_svg,
)
from hibs_racing.models.feature_importance import FeatureImportanceRow


def test_render_importance_svg():
    rows = [
        FeatureImportanceRow("rpr_vs_field", 100, 50, 40.0, 20.0, 1),
        FeatureImportanceRow("sectional_composite", 80, 40, 32.0, 16.0, 2),
    ]
    svg = render_importance_svg(rows)
    assert "<svg" in svg
    assert "rpr_vs_field" in svg


def test_feature_groups_cover_nlp():
    assert "sectional_composite" in FEATURE_GROUPS["nlp_tactical"]
    assert "finishing_burst_level" in FEATURE_GROUPS["nlp_tactical"]


def test_load_feature_impact_report_missing(tmp_path, monkeypatch):
    monkeypatch.setattr("hibs_racing.models.feature_impact.model_dir", lambda cfg=None: tmp_path)
    assert load_feature_impact_report() is None
