from __future__ import annotations

import math
from typing import Any

GATE_LABELS: dict[str, str] = {
    "unrated_race_expected": "Maiden/novice — rank only",
    "missing_or": "No official rating",
    "below_or_floor": "OR below floor",
    "poor_distance_record": "Poor distance record",
    "cold_trainer": "Cold trainer RTF",
    "poor_recent_form": "Poor recent form",
}


def _int(val: object) -> int | None:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        return int(val)
    except (TypeError, ValueError):
        return None


def _float(val: object) -> float | None:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def format_gate_reason(code: object) -> str | None:
    if code is None or (isinstance(code, float) and math.isnan(code)):
        return None
    text = str(code).strip()
    if not text:
        return None
    return GATE_LABELS.get(text, text.replace("_", " ").capitalize())


def _fit_row(label: str, wins: object, runs: object) -> dict[str, str] | None:
    w, r = _int(wins), _int(runs)
    if w is None or r is None:
        return None
    pct = f"{100 * w / r:.0f}%" if r > 0 else "—"
    return {"label": label, "value": f"{w} wins from {r} runs ({pct})"}


def build_enrich_display(row: dict[str, Any]) -> dict[str, Any]:
    """
    Human-readable RP enrich for the card UI — factual only, missing fields omitted.
    """
    fit_rows: list[dict[str, str]] = []
    for label, wk, rk in (
        ("At this course", "horse_course_wins", "horse_course_runs"),
        ("At this trip", "horse_distance_wins", "horse_distance_runs"),
        ("On this going", "horse_going_wins", "horse_going_runs"),
    ):
        item = _fit_row(label, row.get(wk), row.get(rk))
        if item:
            fit_rows.append(item)

    flags: list[dict[str, str]] = []
    if _int(row.get("form_cd_flag")):
        flags.append({"code": "CD", "label": "Won at course & distance before"})
    if _int(row.get("form_bf_flag")):
        flags.append({"code": "BF", "label": "Beaten favourite last time out"})

    trip_label: str | None = None
    trip = _float(row.get("form_trip_change_f"))
    if trip is not None and abs(trip) >= 0.5:
        if trip > 0:
            trip_label = f"Up {trip:.0f}f in trip vs last run"
        else:
            trip_label = f"Down {abs(trip):.0f}f in trip vs last run"

    lto = _int(row.get("form_lto_position"))
    lto_label = f"Last run: {lto}" if lto is not None else None

    rtf = _float(row.get("trainer_rtf"))
    rtf_label = f"Trainer RTF {rtf:.0f}%" if rtf is not None else None

    j14_w, j14_r = _int(row.get("jockey_rp_14d_wins")), _int(row.get("jockey_rp_14d_runs"))
    jockey_14d = (
        f"Jockey 14d: {j14_w} wins from {j14_r} runs"
        if j14_w is not None and j14_r is not None
        else None
    )

    gate_label = format_gate_reason(row.get("value_gate_reason"))

    return {
        "enrich_fit_rows": fit_rows,
        "enrich_flags": flags,
        "enrich_trip_label": trip_label,
        "enrich_lto_label": lto_label,
        "enrich_rtf_label": rtf_label,
        "enrich_jockey_14d_label": jockey_14d,
        "enrich_source": row.get("enrich_source"),
        "value_gate_label": gate_label,
        "enrich_has_data": bool(
            fit_rows or flags or trip_label or lto_label or rtf_label or jockey_14d or row.get("enrich_source")
        ),
        "enrich_fit_line": " · ".join(f"{r['label']}: {r['value']}" for r in fit_rows) if fit_rows else None,
        "enrich_meta_line": " · ".join(p for p in (rtf_label, jockey_14d) if p) or None,
        "enrich_trip": trip_label,
        "enrich_flags_codes": [f["code"] for f in flags],
        "enrich_tooltip": " · ".join(
            p
            for p in (
                *(r["label"] + ": " + r["value"] for r in fit_rows),
                *(f["label"] for f in flags),
                trip_label,
                lto_label,
                rtf_label,
                jockey_14d,
            )
            if p
        )
        or None,
    }
