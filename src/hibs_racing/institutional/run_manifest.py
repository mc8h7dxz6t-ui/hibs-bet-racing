"""Run manifest persistence — ties each score/refresh to config + model identity."""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import json

from hibs_racing.backtest.snapshot_store import scoring_config_hash
from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.institutional.contracts import RunManifest


def _git_sha() -> str | None:
    try:
        root = Path(__file__).resolve().parents[3]
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        sha = (out.stdout or "").strip()
        return sha or None
    except (OSError, subprocess.SubprocessError):
        return os.environ.get("HIBS_GIT_SHA")


def _model_version() -> str:
    cfg = load_config()
    model_dir = Path(cfg.get("paths", {}).get("model_dir", "data/models"))
    ranker = cfg.get("ranker", {})
    model_file = str(ranker.get("model_file", "lgbm_ranker.txt"))
    path = model_dir / model_file if not Path(model_file).is_absolute() else Path(model_file)
    if path.exists():
        return f"{model_file}:{int(path.stat().st_mtime)}"
    return model_file


def build_run_manifest(
    *,
    run_kind: str,
    card_date: str | None = None,
    scoring_method: str | None = None,
    odds_source: str | None = None,
    runner_count: int = 0,
    value_flag_count: int = 0,
    extras: dict[str, Any] | None = None,
    paper_cfg: dict | None = None,
) -> RunManifest:
    created = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    cfg_hash = scoring_config_hash(paper_cfg)
    manifest_id = uuid.uuid4().hex[:16]
    manifest = RunManifest(
        manifest_id=manifest_id,
        run_kind=run_kind,
        card_date=card_date,
        config_hash=cfg_hash,
        model_version=_model_version(),
        scoring_method=scoring_method,
        git_sha=_git_sha(),
        odds_source=odds_source,
        runner_count=runner_count,
        value_flag_count=value_flag_count,
        created_at=created,
        extras=extras or {},
    )
    return manifest


def persist_run_manifest(manifest: RunManifest, database: Path | None = None) -> str:
    db = database or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO run_manifests (
                manifest_id, manifest_hash, run_kind, card_date, config_hash,
                model_version, scoring_method, git_sha, odds_source,
                runner_count, value_flag_count, extras_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                manifest.manifest_id,
                manifest.manifest_hash,
                manifest.run_kind,
                manifest.card_date,
                manifest.config_hash,
                manifest.model_version,
                manifest.scoring_method,
                manifest.git_sha,
                manifest.odds_source,
                manifest.runner_count,
                manifest.value_flag_count,
                json.dumps({"extras": manifest.extras}, sort_keys=True, default=str) if manifest.extras else None,
                manifest.created_at,
            ),
        )
        conn.commit()
    return manifest.manifest_id


def latest_manifest_for_date(card_date: str, database: Path | None = None) -> RunManifest | None:
    db = database or db_path(load_config())
    init_db(db)
    with connect(db) as conn:
        row = conn.execute(
            """
            SELECT manifest_id, run_kind, card_date, config_hash, model_version,
                   scoring_method, git_sha, odds_source, runner_count, value_flag_count,
                   extras_json, created_at
            FROM run_manifests
            WHERE card_date = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (card_date,),
        ).fetchone()
    if not row:
        return None
    import json

    extras: dict = {}
    try:
        raw = row[10]
        if raw:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                extras = parsed.get("extras", parsed)
    except json.JSONDecodeError:
        pass
    return RunManifest(
        manifest_id=row[0],
        run_kind=row[1],
        card_date=row[2],
        config_hash=row[3],
        model_version=row[4],
        scoring_method=row[5],
        git_sha=row[6],
        odds_source=row[7],
        runner_count=int(row[8] or 0),
        value_flag_count=int(row[9] or 0),
        created_at=row[11],
        extras=extras,
    )
