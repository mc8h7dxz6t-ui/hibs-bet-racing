from hibs_racing.models.ranker_attribution import (
    _merge_attribution_rows,
    verify_feature_manifest,
)
from hibs_racing.models.feature_importance import FeatureImportanceRow


def test_verify_feature_manifest_ok():
    features = ["a", "b", "c"]
    check = verify_feature_manifest(features, features)
    assert check["ok"] is True
    assert check["order_match"] is True
    assert check["missing_in_model"] == []


def test_verify_feature_manifest_mismatch():
    manifest = ["a", "b", "c"]
    booster = ["a", "x", "c"]
    check = verify_feature_manifest(manifest, booster)
    assert check["ok"] is False
    assert "b" in check["missing_in_model"]
    assert "x" in check["extra_in_model"]


def test_merge_attribution_rows():
    gain = [
        FeatureImportanceRow("rpr_vs_field", 100, 50, 60.0, 20.0, 1),
        FeatureImportanceRow("combo_bayes_place", 50, 25, 30.0, 10.0, 2),
    ]
    shap = {"rpr_vs_field": 0.12, "combo_bayes_place": 0.08}
    rows = _merge_attribution_rows(gain, shap)
    assert rows[0]["feature"] == "rpr_vs_field"
    assert rows[0]["gain_pct"] == 60.0
    assert rows[0]["shap_pct"] is not None


def test_live_ranker_attribution_smoke():
    from hibs_racing.models.ranker_attribution import live_ranker_attribution

    report = live_ranker_attribution()
    assert "matrix" in report
    assert "checks" in report
    assert "manifest_features" in report
    assert report["feature_count"] >= 30
