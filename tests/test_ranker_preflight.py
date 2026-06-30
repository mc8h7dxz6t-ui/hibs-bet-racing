"""Ranker preflight verification tests."""

from __future__ import annotations

import json

import pytest

from hibs_racing.models.ranker_preflight import RankerPreflightError, observation_lane_enabled, verify_ranker_artifacts


def test_verify_ranker_artifacts_ok(tmp_path):
    mp = tmp_path / "lgbm_ranker.txt"
    fp = tmp_path / "lgbm_ranker_features.json"
    mp.write_text("model-bytes", encoding="utf-8")
    features = ["a", "b"]
    fp.write_text(json.dumps(features), encoding="utf-8")
    manifest_path = tmp_path / "ranker_manifest.json"
    manifest_path.write_text(
        json.dumps({"features": features, "stable_hash": "abc123"}),
        encoding="utf-8",
    )
    report = verify_ranker_artifacts(
        model_path=mp,
        feature_path=fp,
        manifest_path=manifest_path,
    )
    assert report["ok"] is True
    assert report["feature_count"] == 2
    assert len(report["model_sha256"]) == 64
    assert report["manifest_stable_hash"] == "abc123"


def test_verify_ranker_artifacts_manifest_mismatch(tmp_path):
    mp = tmp_path / "lgbm_ranker.txt"
    fp = tmp_path / "lgbm_ranker_features.json"
    mp.write_text("model", encoding="utf-8")
    fp.write_text(json.dumps(["a", "b"]), encoding="utf-8")
    manifest_path = tmp_path / "ranker_manifest.json"
    manifest_path.write_text(json.dumps({"features": ["a", "c"]}), encoding="utf-8")
    with pytest.raises(RankerPreflightError, match="mismatch"):
        verify_ranker_artifacts(
            model_path=mp,
            feature_path=fp,
            manifest_path=manifest_path,
        )


def test_verify_ranker_artifacts_missing_model(tmp_path):
    fp = tmp_path / "lgbm_ranker_features.json"
    fp.write_text("[]", encoding="utf-8")
    with pytest.raises(RankerPreflightError, match="missing"):
        verify_ranker_artifacts(
            model_path=tmp_path / "missing.txt",
            feature_path=fp,
        )


def test_observation_lane_defaults_off_in_production(monkeypatch):
    monkeypatch.delenv("HIBS_OBSERVATION_LANE", raising=False)
    monkeypatch.setenv("HIBS_RACING_PRODUCTION", "1")
    assert observation_lane_enabled() is False


def test_observation_lane_defaults_on_in_dev(monkeypatch):
    monkeypatch.delenv("HIBS_OBSERVATION_LANE", raising=False)
    monkeypatch.delenv("HIBS_RACING_PRODUCTION", raising=False)
    assert observation_lane_enabled() is True


def test_verify_ranker_artifacts_model_sha256_mismatch(tmp_path):
    mp = tmp_path / "lgbm_ranker.txt"
    fp = tmp_path / "lgbm_ranker_features.json"
    mp.write_text("model-v1", encoding="utf-8")
    features = ["a", "b"]
    fp.write_text(json.dumps(features), encoding="utf-8")
    manifest_path = tmp_path / "ranker_manifest.json"
    manifest_path.write_text(
        json.dumps({"features": features, "model_sha256": "0" * 64}),
        encoding="utf-8",
    )
    with pytest.raises(RankerPreflightError, match="model_sha256 mismatch"):
        verify_ranker_artifacts(
            model_path=mp,
            feature_path=fp,
            manifest_path=manifest_path,
        )
