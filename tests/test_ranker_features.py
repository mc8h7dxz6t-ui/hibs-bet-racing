from pathlib import Path

from hibs_racing.ranker_features import resolve_ranker_feature_path


def test_resolve_ranker_feature_path_defaults_base(tmp_path, monkeypatch):
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    base = model_dir / "lgbm_ranker_features.json"
    base.write_text('{"features": ["a", "b"]}', encoding="utf-8")
    cfg = {
        "paths": {"model_dir": str(model_dir), "db_path": "data/feature_store.sqlite"},
        "ranker": {
            "model_file": "lgbm_ranker.txt",
            "feature_file": "lgbm_ranker_features.json",
            "enrich_feature_file": "lgbm_ranker_features_enrich.json",
            "use_enrich_features": "false",
        },
    }
    monkeypatch.delenv("HIBS_USE_ENRICH_RANKER", raising=False)
    assert resolve_ranker_feature_path(cfg) == base
