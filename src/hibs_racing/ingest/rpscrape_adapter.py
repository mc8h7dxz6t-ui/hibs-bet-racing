from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from hibs_racing.entity.natural_key import generate_natural_key, normalize_off_time
from hibs_racing.config import load_config

_DIST_F_RE = re.compile(r"([\d.]+)\s*f")


def _parse_dist_f(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    match = _DIST_F_RE.search(text)
    if match:
        return float(match.group(1))
    try:
        return float(text)
    except ValueError:
        return None


def _race_type(value: object) -> str | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    text = str(value).strip().lower()
    if "flat" in text:
        return "flat"
    if any(x in text for x in ("hurdle", "chase", "nh")):
        return "jumps"
    if "aw" in text or "all weather" in text:
        return "aw"
    return text or None


def _race_id(row: pd.Series) -> str:
    parts = [
        str(row.get("date", "")).strip(),
        str(row.get("course", "")).strip().replace(" ", "_"),
        str(row.get("off", "")).strip().replace(":", ""),
        str(row.get("race_name", "")).strip()[:40].replace(" ", "_"),
    ]
    return "_".join(p for p in parts if p)


def normalize_rpscrape_csv(
    source: Path,
    *,
    output: Path | None = None,
    require_comment: bool | None = None,
) -> Path:
    """
    Convert rpscrape CSV → hibs-racing ingest schema.
    Requires rpscrape columns: date, course, off, race_name, horse, pos, comment.
    """
    frame = pd.read_csv(source)
    required = {"date", "horse", "pos", "comment"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Not an rpscrape CSV — missing columns: {sorted(missing)}")

    out = pd.DataFrame()
    out["race_id"] = frame.apply(_race_id, axis=1)
    out["race_date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    out["horse_id"] = frame["horse"].astype(str).str.strip()
    out["finish_pos"] = pd.to_numeric(frame["pos"], errors="coerce").astype("Int64")
    out["comment"] = frame["comment"].fillna("").astype(str).str.strip()

    if "course" in frame.columns:
        out["course"] = frame["course"]
    if "region" in frame.columns:
        out["region"] = frame["region"]
    if "type" in frame.columns:
        out["race_type"] = frame["type"].map(_race_type)
    if "dist_f" in frame.columns:
        out["distance_f"] = frame["dist_f"].map(_parse_dist_f)
    if "going" in frame.columns:
        out["going"] = frame["going"]
    if "ran" in frame.columns:
        out["field_size"] = pd.to_numeric(frame["ran"], errors="coerce").astype("Int64")
    if "dec" in frame.columns:
        out["sp_decimal"] = pd.to_numeric(frame["dec"], errors="coerce")
    if "jockey" in frame.columns:
        out["jockey"] = frame["jockey"].fillna("").astype(str).str.strip()
    if "trainer" in frame.columns:
        out["trainer"] = frame["trainer"].fillna("").astype(str).str.strip()
    if "draw" in frame.columns:
        out["draw"] = pd.to_numeric(frame["draw"], errors="coerce").astype("Int64")
    if "or" in frame.columns:
        out["official_rating"] = pd.to_numeric(frame["or"], errors="coerce").astype("Int64")
    if "rpr" in frame.columns:
        out["rpr"] = pd.to_numeric(frame["rpr"], errors="coerce").astype("Int64")
    if "class" in frame.columns:
        out["race_class"] = frame["class"].fillna("").astype(str).str.strip()
    if "off" in frame.columns:
        out["off_time"] = frame["off"].astype(str).str.strip()

    cfg = load_config()
    need_comment = (
        require_comment
        if require_comment is not None
        else cfg.get("ingest", {}).get("results_require_comment", True)
    )
    out["comment"] = out["comment"].fillna("").astype(str).str.strip()
    if need_comment:
        out = out[out["comment"].str.len() > 0].copy()
    out["race_natural_key"] = [
        generate_natural_key(str(d)[:10], c, normalize_off_time(t))
        for d, c, t in zip(
            out["race_date"],
            out.get("course", pd.Series([None] * len(out))),
            out.get("off_time", pd.Series([None] * len(out))),
            strict=False,
        )
    ]
    out["runner_id"] = (
        out["race_id"].astype(str) + ":" + out["horse_id"].str.lower().str.replace(r"\s+", "_", regex=True)
    )

    target = output or source.parent / f"hibs_{source.stem}.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(target, index=False)
    return target


def collect_rpscrape_csvs(
    start: date,
    end: date,
    *,
    region: str = "gb",
    race_type: str = "flat",
) -> list[Path]:
    from hibs_racing.ingest.scrape import collect_csvs_in_range

    return collect_csvs_in_range(start, end, region=region, race_type=race_type)


def normalize_rpscrape_files(
    sources: list[Path],
    *,
    output_dir: Path,
    require_comment: bool | None = None,
) -> Path:
    """Merge multiple rpscrape CSVs into one hibs-racing ingest file."""
    if not sources:
        raise ValueError("no source CSV files")
    output_dir.mkdir(parents=True, exist_ok=True)
    parts = [normalize_rpscrape_csv(path, require_comment=require_comment) for path in sources]
    merged = pd.concat([pd.read_csv(p) for p in parts], ignore_index=True)
    merged = merged.drop_duplicates(subset=["runner_id"], keep="last")
    target = output_dir / "results_merged.csv"
    merged.to_csv(target, index=False)
    return target
