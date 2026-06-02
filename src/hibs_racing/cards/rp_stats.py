from __future__ import annotations

from typing import Any


def _split_wins_runs(value: object) -> tuple[int | None, int | None]:
    if value is None:
        return None, None
    if isinstance(value, dict):
        raw = value.get("winsRuns") or value.get("wins_runs")
    else:
        raw = value
    if not raw:
        return None, None
    text = str(raw).strip()
    if "-" not in text:
        return None, None
    wins_s, runs_s = text.split("-", 1)
    try:
        return int(wins_s.strip()), int(runs_s.strip())
    except ValueError:
        return None, None


def _win_rate(wins: int | None, runs: int | None) -> float | None:
    if wins is None or runs is None or runs <= 0:
        return None
    return wins / runs


def _segment_wins_runs(segment: dict | None) -> tuple[int | None, int | None]:
    if not segment or not isinstance(segment, dict):
        return None, None
    if "winsRuns" in segment:
        return _split_wins_runs(segment.get("winsRuns"))
    return _int_or_none(segment.get("wins") or segment.get("last_14_wins")), _int_or_none(
        segment.get("runs") or segment.get("last_14_runs")
    )


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_horse_stats(horse_stats: dict | None) -> dict[str, Any]:
    """RP accordion horse course / distance / going wins-runs."""
    out: dict[str, Any] = {}
    if not horse_stats or not isinstance(horse_stats, dict):
        return out
    for key, prefix in (("course", "horse_course"), ("distance", "horse_distance"), ("going", "horse_going")):
        seg = horse_stats.get(key)
        if isinstance(seg, dict) and "wins" in seg and "runs" in seg:
            w, r = _int_or_none(seg.get("wins")), _int_or_none(seg.get("runs"))
        else:
            w, r = _split_wins_runs(seg)
        out[f"{prefix}_wins"] = w
        out[f"{prefix}_runs"] = r
        out[f"{prefix}_win_rate"] = _win_rate(w, r)
    return out


def parse_entity_segment(entity_stats: dict | None, *, prefix: str) -> dict[str, Any]:
    """Jockey/trainer RP 14d + overall segments from stats accordion."""
    out: dict[str, Any] = {}
    if not entity_stats or not isinstance(entity_stats, dict):
        return out
    last14 = entity_stats.get("last14Days") if "last14Days" in entity_stats else entity_stats
    if isinstance(last14, dict) and any(k in last14 for k in ("winsRuns", "wins", "runs", "last_14_wins")):
        w, r = _segment_wins_runs(last14)
    else:
        w = _int_or_none(entity_stats.get("last_14_wins"))
        r = _int_or_none(entity_stats.get("last_14_runs"))
        if w is None and r is None:
            w, r = _segment_wins_runs(entity_stats)
    out[f"{prefix}_14d_wins"] = w
    out[f"{prefix}_14d_runs"] = r
    out[f"{prefix}_14d_win_rate"] = _win_rate(w, r)
    pct = entity_stats.get("last_14_wins_pct")
    if pct is None:
        pct = last14.get("strike_rate") if isinstance(last14, dict) else None
    out[f"{prefix}_14d_wins_pct"] = _float_or_none(pct)
    return out


def flatten_runner_stats(stats: object) -> dict[str, Any]:
    """Flatten runner.stats dict from rpscrape racecard JSON."""
    if not stats or not isinstance(stats, dict):
        return {}
    out: dict[str, Any] = {}
    out.update(parse_horse_stats(stats.get("horse")))
    out.update(parse_entity_segment(stats.get("jockey"), prefix="jockey_rp"))
    out.update(parse_entity_segment(stats.get("trainer"), prefix="trainer_rp"))
    return out
