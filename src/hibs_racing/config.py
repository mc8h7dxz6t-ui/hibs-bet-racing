from __future__ import annotations

import os
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_config(path: Path | None = None) -> dict:
    cfg_path = path or ROOT / "ingest" / "config.yaml"
    with cfg_path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def data_dir() -> Path:
    raw = os.environ.get("HIBS_RACING_DATA_DIR", str(ROOT / "data"))
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def db_path(cfg: dict | None = None) -> Path:
    env = os.environ.get("HIBS_RACING_DB_PATH")
    if env:
        return Path(env)
    if cfg:
        return ROOT / cfg["paths"]["db_path"]
    return data_dir() / "feature_store.sqlite"


def model_dir(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    raw = cfg.get("paths", {}).get("model_dir", "data/models")
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


def ranker_model_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    fname = cfg.get("ranker", {}).get("model_file", "lgbm_ranker.txt")
    return model_dir(cfg) / fname


def ranker_feature_path(cfg: dict | None = None) -> Path:
    cfg = cfg or load_config()
    fname = cfg.get("ranker", {}).get("feature_file", "lgbm_ranker_features.json")
    return model_dir(cfg) / fname
