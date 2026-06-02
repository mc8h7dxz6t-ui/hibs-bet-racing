from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from hibs_racing.cards.form_parser import parse_form_string
from hibs_racing.cards.rp_stats import flatten_runner_stats
from hibs_racing.ingest.rate_limit import polite_sleep, rp_racecard_region_pause
from hibs_racing.config import ROOT, load_config
from hibs_racing.entity.natural_key import generate_natural_key, normalize_course, normalize_off_time
from hibs_racing.odds.matching import normalize_horse_name

RPSCRAPE_SETTINGS = ROOT / "vendor" / "rpscrape" / "settings" / "user_racecard_settings.toml"

# Spine fields — never overwrite non-null API values during merge.
_PROTECTED_OVERWRITE = frozenset(
    {
        "official_rating",
        "rpr",
        "draw",
        "horse_id",
        "win_decimal",
        "race_id",
        "runner_id",
        "field_size",
        "distance_f",
    }
)

ENRICH_MERGE_COLUMNS = (
    "form_string",
    "card_comment",
    "trainer_rtf",
    "trainer_14d_wins",
    "trainer_14d_runs",
    "trainer_location",
    "rp_verdict",
    "horse_course_wins",
    "horse_course_runs",
    "horse_course_win_rate",
    "horse_distance_wins",
    "horse_distance_runs",
    "horse_distance_win_rate",
    "horse_going_wins",
    "horse_going_runs",
    "horse_going_win_rate",
    "jockey_rp_14d_wins",
    "jockey_rp_14d_runs",
    "jockey_rp_14d_win_rate",
    "jockey_rp_14d_wins_pct",
    "trainer_rp_14d_wins",
    "trainer_rp_14d_runs",
    "trainer_rp_14d_win_rate",
    "trainer_rp_14d_wins_pct",
    "form_lto_position",
    "form_trip_change_f",
    "form_cd_flag",
    "form_bf_flag",
    "form_poor_runs_3",
)

ENRICH_RANKER_FEATURES = (
    "horse_course_win_rate",
    "horse_distance_win_rate",
    "horse_going_win_rate",
    "jockey_rp_14d_win_rate",
    "trainer_rp_14d_win_rate",
    "trainer_rtf",
    "trainer_14d_strike",
    "form_lto_position",
    "form_trip_change_f",
    "form_cd_flag",
    "form_bf_flag",
    "form_poor_runs_3",
)


def enrich_ranker_feature_columns() -> list[str]:
    from hibs_racing.features.ranker_matrix import ranker_feature_columns

    return ranker_feature_columns() + list(ENRICH_RANKER_FEATURES)


def _is_empty(val: object) -> bool:
    if val is None:
        return True
    if isinstance(val, float) and pd.isna(val):
        return True
    if isinstance(val, str) and not val.strip():
        return True
    return False


def ensure_rp_stats_settings(*, fetch_stats: bool = True) -> None:
    """Enable RP stats accordion fetch in vendor rpscrape (merge-only enrich)."""
    RPSCRAPE_SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    text = RPSCRAPE_SETTINGS.read_text(encoding="utf-8") if RPSCRAPE_SETTINGS.exists() else ""
    want = f"fetch_stats = {str(fetch_stats).lower()}"
    if "fetch_stats" in text:
        import re

        text = re.sub(r"fetch_stats\s*=\s*\w+", want, text)
    else:
        block = f"[data_collection]\n{want}\nfetch_profiles = false\nmax_days = 2\n"
        text = block if not text.strip() else f"{text.rstrip()}\n\n{block}"
    RPSCRAPE_SETTINGS.write_text(text, encoding="utf-8")


def enrich_join_key(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["card_date"].astype(str).str[:10]
        + "|"
        + frame["course"].map(lambda c: normalize_course(c) or "")
        + "|"
        + frame["off_time"].map(lambda t: normalize_off_time(t) if t is not None else "")
        + "|"
        + frame["horse_name"].map(lambda h: normalize_horse_name(h))
    )


def apply_form_enrich(frame: pd.DataFrame) -> pd.DataFrame:
    """Derive form_* columns from form_string + today distance (in-place safe copy)."""
    out = frame.copy()
    rows: list[dict[str, Any]] = []
    for rec in out.to_dict(orient="records"):
        parsed = parse_form_string(rec.get("form_string"), today_distance_f=rec.get("distance_f"))
        rows.append(parsed)
    if rows:
        parsed_df = pd.DataFrame(rows, index=out.index)
        for col in parsed_df.columns:
            if col not in out.columns or out[col].isna().all():
                out[col] = parsed_df[col]
            else:
                out[col] = out[col].combine_first(parsed_df[col])
    if "trainer_14d_wins" in out.columns and "trainer_14d_runs" in out.columns:
        w = pd.to_numeric(out["trainer_14d_wins"], errors="coerce")
        r = pd.to_numeric(out["trainer_14d_runs"], errors="coerce")
        out["trainer_14d_strike"] = (w / r).where(r > 0)
    return out


def compute_enrich_ranker_fields(frame: pd.DataFrame) -> pd.DataFrame:
    """Ensure derived ranker-ready enrich columns exist (NaN when missing)."""
    out = frame.copy()
    out = apply_form_enrich(out)
    if "trainer_14d_strike" not in out.columns and "trainer_14d_wins" in out.columns:
        w = pd.to_numeric(out["trainer_14d_wins"], errors="coerce")
        r = pd.to_numeric(out["trainer_14d_runs"], errors="coerce")
        out["trainer_14d_strike"] = (w / r).where(r > 0)
    if "trainer_rtf" in out.columns:
        out["trainer_rtf"] = pd.to_numeric(out["trainer_rtf"], errors="coerce")
    for col in ENRICH_RANKER_FEATURES:
        if col not in out.columns:
            out[col] = pd.NA
    return out


def merge_null_only(spine: pd.DataFrame, enrich: pd.DataFrame) -> pd.DataFrame:
    """
    Merge RP enrich rows onto Racing API spine — fill nulls only on enrich columns.
    Join: card_date + course + off_time + horse_name (not race_id — differs by source).
    """
    if spine.empty or enrich.empty:
        return apply_form_enrich(spine)

    left = spine.copy()
    right = enrich.copy()
    left["_ej"] = enrich_join_key(left)
    right["_ej"] = enrich_join_key(right)

    right = right.drop_duplicates(subset=["_ej"], keep="last")
    right_indexed = right.set_index("_ej")

    for col in ENRICH_MERGE_COLUMNS:
        if col not in right_indexed.columns:
            continue
        if col not in left.columns:
            left[col] = pd.NA
        mapped = left["_ej"].map(right_indexed[col])
        if col in _PROTECTED_OVERWRITE:
            continue
        mask = left[col].map(_is_empty)
        left.loc[mask, col] = mapped[mask]

    # Second pass: protected fields only when spine empty
    for col in ("card_comment", "form_string", "trainer_rtf", "trainer_14d_wins", "trainer_14d_runs"):
        if col not in right_indexed.columns:
            continue
        if col not in left.columns:
            left[col] = pd.NA
        mapped = left["_ej"].map(right_indexed[col])
        mask = left[col].map(_is_empty)
        left.loc[mask, col] = mapped[mask]

    if "rp_verdict" in right_indexed.columns:
        if "rp_verdict" not in left.columns:
            left["rp_verdict"] = pd.NA
        mask = left["rp_verdict"].map(_is_empty)
        left.loc[mask, "rp_verdict"] = left["_ej"].map(right_indexed["rp_verdict"])[mask]

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    matched = left["_ej"].isin(right_indexed.index)
    left["enrich_source"] = None
    left.loc[matched, "enrich_source"] = "rpscrape"
    left["enriched_at"] = None
    left.loc[matched, "enriched_at"] = now
    left = left.drop(columns=["_ej"])
    return apply_form_enrich(left)


def fetch_rp_enrich_frame(
    *,
    day: int = 1,
    regions: tuple[str, ...] = ("gb", "ire"),
) -> pd.DataFrame:
    """Fetch rpscrape racecards with stats for dual-source enrich (best-effort)."""
    cfg = load_config().get("cards", {})
    if not cfg.get("dual_source_enrich", True):
        return pd.DataFrame()
    if cfg.get("enrich_fetch_stats", True):
        ensure_rp_stats_settings(fetch_stats=True)

    from hibs_racing.ingest.racecards import load_racecard_frames

    frames: list[pd.DataFrame] = []
    for i, region in enumerate(regions):
        if i > 0:
            polite_sleep("rp_racecard_region_pause_sec")
        try:
            frames.append(load_racecard_frames(day=day, region=region))
        except Exception:
            if region == regions[0]:
                raise
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def dual_source_enrich(
    spine: pd.DataFrame,
    *,
    regions: tuple[str, ...] = ("gb", "ire"),
    day: int = 1,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """
    Racing API spine + RP enrich merge. Failures return spine unchanged (no regression).
    """
    meta: dict[str, Any] = {"attempted": True, "matched": 0, "runners": len(spine)}
    if spine.empty:
        return spine, meta
    cfg = load_config().get("cards", {})
    if not cfg.get("dual_source_enrich", True):
        meta["attempted"] = False
        return apply_form_enrich(spine), meta

    try:
        enrich = fetch_rp_enrich_frame(day=day, regions=regions)
    except Exception as exc:
        meta["error"] = str(exc)[:200]
        return apply_form_enrich(spine), meta

    if enrich.empty:
        meta["error"] = "no_rp_rows"
        return apply_form_enrich(spine), meta

    merged = merge_null_only(spine, enrich)
    keys = enrich_join_key(spine)
    enrich_keys = set(enrich_join_key(enrich))
    meta["matched"] = int(keys.isin(enrich_keys).sum())
    meta["rp_runners"] = len(enrich)
    return merged, meta


def parse_runner_row_enrich(runner: dict) -> dict[str, Any]:
    """Extract enrich fields from a single rpscrape runner dict."""
    out = flatten_runner_stats(runner.get("stats"))
    form = runner.get("form") or runner.get("form_string") or ""
    out.update(parse_form_string(form, today_distance_f=runner.get("distance_f")))
    return out
