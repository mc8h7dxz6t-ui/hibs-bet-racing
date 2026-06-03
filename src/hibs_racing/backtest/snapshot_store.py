"""Immutable scored-card snapshots for fast gate replay and audit manifests."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.cards.harville_config import harville_runtime_config
from hibs_racing.config import load_config
from hibs_racing.features.store import connect, init_db

# Runner fields explicitly mirrored in scored_runner_snapshots columns.
SNAPSHOT_CORE_KEYS: frozenset[str] = frozenset(
    {
        "card_date",
        "runner_id",
        "race_id",
        "odds_source",
        "config_hash",
        "course",
        "race_name",
        "field_size",
        "official_rating",
        "win_decimal",
        "place_fraction",
        "places",
        "model_score",
        "model_win_prob",
        "model_place_prob",
        "combo_bayes_place",
        "place_ev",
        "ew_combined_ev",
        "flag_raw",
        "finish_pos",
        "scored_at",
        "manifest_json",
        "gates_json",
        "value_flag",
        "value_gate_reason",
    }
)

# Explicit gate / DQ replay keys (merged into gates_json even if also in frame).
GATE_CONTEXT_KEYS: tuple[str, ...] = (
    "race_name",
    "card_comment",
    "jockey",
    "trainer",
    "enrich_source",
    "form_string",
    "horse_course_win_rate",
    "trainer_rtf",
    "horse_distance_runs",
    "horse_distance_wins",
    "form_trip_change_f",
    "form_poor_runs_3",
    "jockey_bayes_place",
    "trainer_bayes_place",
    "steam_gate",
)

# Keys that affect scoring / gate replay — bump invalidates snapshot rows.
_CONFIG_HASH_KEYS: tuple[str, ...] = (
    "min_place_ev",
    "min_combo_bayes_place",
    "harville_longshot_win_prob_threshold",
    "harville_longshot_discount",
    "default_place_fraction",
    "default_places",
    "value_gates_enabled",
    "exempt_unrated_races",
    "require_official_rating_for_value",
    "min_official_rating",
    "suitability_gates_enabled",
    "min_horse_dist_runs",
    "block_zero_dist_wins",
    "max_trip_change_f",
    "max_form_poor_runs_3",
    "min_trainer_rtf",
    "min_data_quality_pct",
    "enforce_steam_gate",
    "allowed_steam_gates",
    "gate2",
)


def _model_version_stamp(cfg: dict) -> str:
    """Ranker artifact identity — snapshots must not mix scores across retrains."""
    model_dir = Path(cfg.get("paths", {}).get("model_dir", "data/models"))
    ranker = cfg.get("ranker", {})
    model_file = str(ranker.get("model_file", "lgbm_ranker.txt"))
    path = model_dir / model_file if not Path(model_file).is_absolute() else Path(model_file)
    if path.exists():
        return f"{model_file}:{int(path.stat().st_mtime)}"
    return model_file


def scoring_config_hash(paper_cfg: dict | None = None) -> str:
    """Stable hash of paper gates, Harville, and ranker manifest that affect scoring replay."""
    full = load_config()
    cfg = paper_cfg if paper_cfg is not None else full.get("paper", {})
    subset: dict[str, Any] = {}
    for key in _CONFIG_HASH_KEYS:
        if key in cfg:
            subset[key] = cfg[key]
    hv = harville_runtime_config(full)
    subset["harville_effective_discount"] = hv["effective_discount"]
    subset["harville_correction_env"] = hv["correction_env"]
    subset["model_version"] = _model_version_stamp(full)
    try:
        from hibs_racing.ranker_features import ranker_feature_profile

        profile = ranker_feature_profile(full)
        subset["ranker_manifest"] = profile.get("feature_manifest")
        subset["uses_enrich_booster"] = profile.get("uses_enrich")
    except Exception:
        pass
    payload = json.dumps(subset, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _gates_blob(rec: dict) -> str | None:
    """Full non-core context for gate replay — preserves enrich / DQ fields without column loss."""
    ctx: dict = {}
    for key, val in rec.items():
        if key in SNAPSHOT_CORE_KEYS:
            continue
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        if isinstance(val, str) and not val.strip():
            continue
        ctx[key] = val
    for key in GATE_CONTEXT_KEYS:
        if key not in rec:
            continue
        val = rec[key]
        if val is None or (isinstance(val, float) and pd.isna(val)):
            continue
        if isinstance(val, str) and not val.strip():
            continue
        ctx[key] = val
    return json.dumps(ctx, sort_keys=True, default=str) if ctx else None


def merge_upcoming_enrich(db: Path, day: pd.DataFrame, card_date: str) -> pd.DataFrame:
    """Overlay RP enrich columns from upcoming_runners when stored for this card date."""
    if day.empty:
        return day
    init_db(db)
    enrich_cols = [
        "runner_id",
        "race_name",
        "form_string",
        "enrich_source",
        "horse_course_win_rate",
        "horse_distance_runs",
        "horse_distance_wins",
        "form_trip_change_f",
        "form_poor_runs_3",
        "trainer_rtf",
    ]
    with connect(db) as conn:
        try:
            up = pd.read_sql_query(
                f"""
                SELECT {", ".join(enrich_cols)}
                FROM upcoming_runners
                WHERE card_date = ?
                """,
                conn,
                params=(str(card_date),),
            )
        except (OSError, ValueError):
            return day
    if up.empty:
        return day
    base = day.drop(columns=[c for c in enrich_cols if c != "runner_id" and c in day.columns], errors="ignore")
    merged = base.merge(up, on="runner_id", how="left", suffixes=("", "_up"))
    for col in enrich_cols:
        if col == "runner_id":
            continue
        up_col = f"{col}_up"
        if up_col in merged.columns:
            if col in merged.columns:
                merged[col] = merged[col].combine_first(merged[up_col])
            else:
                merged[col] = merged[up_col]
            merged = merged.drop(columns=[up_col], errors="ignore")
    return merged


def _expand_gates_json(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty or "gates_json" not in frame.columns:
        return frame
    out = frame.copy()
    for idx, raw in out["gates_json"].items():
        if not raw or not isinstance(raw, str):
            continue
        try:
            ctx = json.loads(raw)
        except json.JSONDecodeError:
            continue
        if isinstance(ctx, dict):
            for key, val in ctx.items():
                out.at[idx, key] = val
    return out


def build_run_manifest(*, card_date: str, odds_source: str, config_hash: str, extra: dict | None = None) -> str:
    body: dict[str, Any] = {
        "card_date": card_date,
        "odds_source": odds_source,
        "config_hash": config_hash,
        "written_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }
    if extra:
        body.update(extra)
    return json.dumps(body, sort_keys=True)


def upsert_snapshots(
    db: Path,
    card_date: str,
    frame: pd.DataFrame,
    *,
    odds_source: str = "sp",
    config_hash: str | None = None,
    finish_by_runner: dict[str, int] | None = None,
    paper_cfg: dict | None = None,
) -> int:
    """
    Persist pre-gate scored rows. ``frame`` must include model outputs and ``flag_raw``.
    """
    if frame.empty:
        return 0
    init_db(db)
    cfg_hash = config_hash or scoring_config_hash(paper_cfg)
    scored_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    manifest = build_run_manifest(card_date=card_date, odds_source=odds_source, config_hash=cfg_hash)
    n = 0
    with connect(db) as conn:
        for rec in frame.to_dict(orient="records"):
            rid = str(rec["runner_id"])
            finish = None
            if finish_by_runner and rid in finish_by_runner:
                finish = int(finish_by_runner[rid])
            elif rec.get("finish_pos") is not None and not (
                isinstance(rec.get("finish_pos"), float) and pd.isna(rec["finish_pos"])
            ):
                finish = int(rec["finish_pos"])
            conn.execute(
                """
                INSERT INTO scored_runner_snapshots (
                    card_date, runner_id, race_id, odds_source, config_hash,
                    course, race_name, field_size, official_rating,
                    win_decimal, place_fraction, places,
                    model_score, model_win_prob, model_place_prob, combo_bayes_place,
                    place_ev, ew_combined_ev, flag_raw, finish_pos, scored_at, manifest_json, gates_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(card_date, runner_id, odds_source, config_hash) DO UPDATE SET
                    race_id=excluded.race_id,
                    course=excluded.course,
                    race_name=excluded.race_name,
                    field_size=excluded.field_size,
                    official_rating=excluded.official_rating,
                    win_decimal=excluded.win_decimal,
                    place_fraction=excluded.place_fraction,
                    places=excluded.places,
                    model_score=excluded.model_score,
                    model_win_prob=excluded.model_win_prob,
                    model_place_prob=excluded.model_place_prob,
                    combo_bayes_place=excluded.combo_bayes_place,
                    place_ev=excluded.place_ev,
                    ew_combined_ev=excluded.ew_combined_ev,
                    flag_raw=excluded.flag_raw,
                    finish_pos=excluded.finish_pos,
                    scored_at=excluded.scored_at,
                    manifest_json=excluded.manifest_json,
                    gates_json=excluded.gates_json
                """,
                (
                    card_date,
                    rid,
                    str(rec["race_id"]),
                    odds_source,
                    cfg_hash,
                    rec.get("course"),
                    rec.get("race_name"),
                    int(rec["field_size"]) if rec.get("field_size") is not None and not pd.isna(rec.get("field_size")) else None,
                    int(rec["official_rating"])
                    if rec.get("official_rating") is not None and not pd.isna(rec.get("official_rating"))
                    else None,
                    float(rec["win_decimal"])
                    if rec.get("win_decimal") is not None and not pd.isna(rec.get("win_decimal"))
                    else None,
                    float(rec.get("place_fraction") or 0.25),
                    int(rec.get("places") or 3)
                    if rec.get("places") is not None and not (isinstance(rec.get("places"), float) and pd.isna(rec.get("places")))
                    else 3,
                    float(rec["model_score"]),
                    rec.get("model_win_prob"),
                    rec.get("model_place_prob"),
                    rec.get("combo_bayes_place"),
                    rec.get("place_ev") if pd.notna(rec.get("place_ev")) else None,
                    rec.get("ew_combined_ev") if pd.notna(rec.get("ew_combined_ev")) else None,
                    int(rec.get("flag_raw") or 0),
                    finish,
                    scored_at,
                    manifest,
                    _gates_blob(rec),
                ),
            )
            n += 1
        conn.commit()
    return n


def load_snapshots(
    db: Path,
    start: str,
    end: str,
    *,
    odds_source: str | None = "sp",
    config_hash: str | None = None,
) -> pd.DataFrame:
    init_db(db)
    cfg_hash = config_hash or scoring_config_hash()
    with connect(db) as conn:
        if odds_source is None:
            frame = pd.read_sql_query(
                """
                SELECT s.*
                FROM scored_runner_snapshots s
                INNER JOIN (
                    SELECT runner_id, card_date, config_hash,
                           MAX(CASE odds_source WHEN 'live' THEN 2 WHEN 'sp' THEN 1 ELSE 0 END) AS src_rank
                    FROM scored_runner_snapshots
                    WHERE card_date >= ? AND card_date <= ? AND config_hash = ?
                    GROUP BY runner_id, card_date, config_hash
                ) pick ON pick.runner_id = s.runner_id
                    AND pick.card_date = s.card_date
                    AND pick.config_hash = s.config_hash
                    AND (
                        (pick.src_rank = 2 AND s.odds_source = 'live')
                        OR (pick.src_rank = 1 AND s.odds_source = 'sp')
                        OR (pick.src_rank = 0 AND s.odds_source = (
                            SELECT odds_source FROM scored_runner_snapshots s2
                            WHERE s2.runner_id = s.runner_id AND s2.card_date = s.card_date
                              AND s2.config_hash = s.config_hash LIMIT 1
                        ))
                    )
                WHERE s.card_date >= ? AND s.card_date <= ? AND s.config_hash = ?
                ORDER BY s.card_date, s.race_id, s.runner_id
                """,
                conn,
                params=(start, end, cfg_hash, start, end, cfg_hash),
            )
        else:
            frame = pd.read_sql_query(
                """
                SELECT *
                FROM scored_runner_snapshots
                WHERE card_date >= ? AND card_date <= ?
                  AND odds_source = ?
                  AND config_hash = ?
                ORDER BY card_date, race_id, runner_id
                """,
                conn,
                params=(start, end, odds_source, cfg_hash),
            )
    return _expand_gates_json(frame)


def load_snapshots_for_card(
    db: Path,
    card_date: str,
    *,
    config_hash: str | None = None,
) -> pd.DataFrame:
    """Prefer live snapshots, fall back to SP historical."""
    for src in ("live", "sp"):
        frame = load_snapshots(db, card_date, card_date, odds_source=src, config_hash=config_hash)
        if not frame.empty:
            return frame
    return load_snapshots(db, card_date, card_date, odds_source=None, config_hash=config_hash)


def snapshot_card_dates(db: Path, start: str, end: str, *, config_hash: str | None = None) -> list[str]:
    init_db(db)
    cfg_hash = config_hash or scoring_config_hash()
    with connect(db) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT card_date
            FROM scored_runner_snapshots
            WHERE card_date >= ? AND card_date <= ?
              AND config_hash = ?
            ORDER BY card_date
            """,
            (start, end, cfg_hash),
        ).fetchall()
    return [str(r[0]) for r in rows]


def snapshot_coverage(
    db: Path,
    start: str,
    end: str,
    *,
    expected_dates: list[str] | None = None,
    config_hash: str | None = None,
) -> dict[str, Any]:
    """Report how many card dates have snapshot rows vs expected historical dates."""
    cfg_hash = config_hash or scoring_config_hash()
    stored = set(snapshot_card_dates(db, start, end, config_hash=cfg_hash))
    if expected_dates is None:
        init_db(db)
        with connect(db) as conn:
            rows = conn.execute(
                """
                SELECT DISTINCT race_date
                FROM runners
                WHERE race_date >= ? AND race_date <= ?
                  AND finish_pos IS NOT NULL AND finish_pos > 0
                  AND sp_decimal IS NOT NULL
                ORDER BY race_date
                """,
                (start, end),
            ).fetchall()
        expected_dates = [str(r[0]) for r in rows]
    expected = set(expected_dates)
    missing = sorted(expected - stored)
    return {
        "start": start,
        "end": end,
        "config_hash": cfg_hash,
        "expected_card_days": len(expected),
        "snapshot_card_days": len(stored),
        "coverage_pct": round(100.0 * len(stored) / len(expected), 2) if expected else 100.0,
        "missing_dates": missing[:20],
        "missing_count": len(missing),
        "complete": len(missing) == 0 and bool(expected),
    }
