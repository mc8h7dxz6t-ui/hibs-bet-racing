from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

COLUMN_ALIASES: dict[str, list[str]] = {
    "race_id": ["race_id", "raceid", "race"],
    "race_date": ["race_date", "date", "off_dt"],
    "horse_id": ["horse_id", "horse", "horse_name", "name"],
    "finish_pos": ["finish_pos", "pos", "position", "fin"],
    "comment": ["comment", "running_comment", "form_comment", "notes"],
    "course": ["course", "venue"],
    "region": ["region", "country"],
    "race_type": ["race_type", "type", "category"],
    "distance_f": ["distance_f", "dist_f", "distance"],
    "going": ["going", "ground"],
    "field_size": ["field_size", "runners", "ran"],
    "sp_decimal": ["sp_decimal", "sp", "starting_price", "dec"],
    "jockey": ["jockey"],
    "trainer": ["trainer"],
    "draw": ["draw", "stall"],
    "official_rating": ["official_rating", "or"],
    "rpr": ["rpr"],
    "race_class": ["race_class", "class"],
    "off_time": ["off_time", "off"],
}


def _resolve_column(df: pd.DataFrame, canonical: str) -> str | None:
    lower_map = {c.lower(): c for c in df.columns}
    for alias in COLUMN_ALIASES.get(canonical, [canonical]):
        if alias in df.columns:
            return alias
        if alias.lower() in lower_map:
            return lower_map[alias.lower()]
    return None


def normalize_csv_frame(df: pd.DataFrame) -> pd.DataFrame:
    mapping: dict[str, str] = {}
    for canonical in COLUMN_ALIASES:
        found = _resolve_column(df, canonical)
        if found:
            mapping[found] = canonical

    out = df.rename(columns=mapping)
    required = {"race_id", "race_date", "horse_id", "finish_pos", "comment"}
    missing = required - set(out.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")

    out["race_date"] = pd.to_datetime(out["race_date"]).dt.strftime("%Y-%m-%d")
    out["finish_pos"] = pd.to_numeric(out["finish_pos"], errors="coerce").astype("Int64")
    if "field_size" in out.columns:
        out["field_size"] = pd.to_numeric(out["field_size"], errors="coerce").astype("Int64")
    if "distance_f" in out.columns:
        out["distance_f"] = pd.to_numeric(out["distance_f"], errors="coerce")
    if "sp_decimal" in out.columns:
        out["sp_decimal"] = pd.to_numeric(out["sp_decimal"], errors="coerce")
    if "draw" in out.columns:
        out["draw"] = pd.to_numeric(out["draw"], errors="coerce").astype("Int64")
    if "official_rating" in out.columns:
        out["official_rating"] = pd.to_numeric(out["official_rating"], errors="coerce").astype("Int64")
    if "rpr" in out.columns:
        out["rpr"] = pd.to_numeric(out["rpr"], errors="coerce").astype("Int64")

    out["runner_id"] = (
        out["race_id"].astype(str)
        + ":"
        + out["horse_id"].astype(str).str.lower().str.replace(r"\s+", "_", regex=True)
    )
    return out


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
