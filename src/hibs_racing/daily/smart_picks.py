"""Morning Smart Portfolio picks — same filters as dashboard JS (novice UX)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from hibs_racing.cards.query import load_scored_cards
from hibs_racing.pick_explain import attach_pick_explanations
from hibs_racing.web_service import dashboard_context, novice_pick_candidates


def filter_smart_picks(candidates: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    from hibs_racing.config import load_config

    paper = load_config().get("paper", {})
    raw_gates = paper.get("allowed_steam_gates", ["proceed", "scale_up", "unknown"])
    if isinstance(raw_gates, (list, tuple)):
        allowed_gates = {str(g).lower() for g in raw_gates}
    else:
        allowed_gates = {"proceed", "scale_up", "unknown"}
    min_dq = int(paper.get("min_data_quality_pct") or 75)
    filtered = [
        c
        for c in candidates
        if c.get("value_flag")
        and not c.get("value_gate_reason")
        and int(c.get("data_quality_pct") or 0) >= min_dq
        and str(c.get("steam_gate") or "proceed").lower() in allowed_gates
    ]
    filtered.sort(
        key=lambda c: float(c.get("place_score") or c.get("model_place_prob") or 0),
        reverse=True,
    )
    return filtered[: max(1, int(limit))]


def _merge_pick_with_frame(pick: dict[str, Any], frame: pd.DataFrame) -> dict[str, Any]:
    """Join UI shortlist row to scored card row for explanations (read-only)."""
    rid = str(pick.get("runner_id") or "")
    if rid and not frame.empty and "runner_id" in frame.columns:
        match = frame[frame["runner_id"].astype(str) == rid]
        if not match.empty:
            row = match.iloc[0].to_dict()
            mpp = row.get("model_place_prob")
            cbp = row.get("combo_bayes_place")
            try:
                ps = float(mpp or 0) * 0.65 + float(cbp or 0) * 0.35
            except (TypeError, ValueError):
                ps = float(pick.get("place_score") or pick.get("model_place_prob") or 0)
            merged = {**row, **pick, "place_score": pick.get("place_score") or ps}
            race_id = row.get("race_id")
            if race_id and "model_score" in frame.columns:
                peers = frame[frame["race_id"] == race_id]
                if not peers.empty and peers["model_score"].notna().any():
                    top = peers.sort_values("model_score", ascending=False).iloc[0]
                    merged["race_top1_horse"] = top.get("horse_name")
            return merged
    return dict(pick)


def build_morning_smart_picks(*, limit: int = 3, window_hours: int = 24) -> dict[str, Any]:
    ctx = dashboard_context(window_hours=window_hours)
    candidates = novice_pick_candidates(ctx.get("meetings") or [])
    picks = filter_smart_picks(candidates, limit=limit)
    return {
        "ok": True,
        "pick_count": len(picks),
        "picks": picks,
        "card_dates": ctx.get("card_dates") or [],
        "scoring_method": ctx.get("scoring_method"),
        "candidate_count": len(candidates),
    }


def build_morning_smart_picks_explained(*, limit: int = 3, window_hours: int = 24) -> dict[str, Any]:
    """Same shortlist as build_morning_smart_picks plus pick_reasons from scored card."""
    base = build_morning_smart_picks(limit=limit, window_hours=window_hours)
    frame = load_scored_cards()
    merged = [_merge_pick_with_frame(p, frame) for p in base.get("picks") or []]
    for i, p in enumerate(merged, start=1):
        p["day_rank"] = i
    explained = attach_pick_explanations(merged, frame) if not frame.empty else merged
    return {
        **base,
        "picks": explained,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
    }


def format_pick_line(pick: dict[str, Any], index: int) -> str:
    horse = pick.get("horse_name") or "?"
    course = pick.get("course") or "?"
    off = pick.get("off_time") or "?"
    dq = pick.get("data_quality_pct") or 0
    gate = pick.get("steam_gate") or "proceed"
    place_pct = round(float(pick.get("model_place_prob") or 0) * 100)
    ev = pick.get("ew_combined_ev")
    ev_s = f"{float(ev):.2f}" if ev is not None else "—"
    win = pick.get("win_decimal")
    win_s = f" · win {float(win):.2f}" if win else ""
    link = pick.get("monetized_link")
    link_s = f"\n   Partner: {link}" if link else ""
    return (
        f"#{index} {horse} ({off} {course})\n"
        f"   Place {place_pct}% · EV {ev_s} · DQ {dq}% · gate {gate}{win_s}{link_s}"
    )


def format_digest_message(payload: dict[str, Any], *, product_name: str = "Hibs Racing Intelligence") -> str:
    picks = payload.get("picks") or []
    dates = ", ".join(payload.get("card_dates") or []) or "today"
    lines = [
        f"🏇 {product_name} — Daily Value Sheet",
        f"Cards: {dates}",
        "",
    ]
    if not picks:
        lines.append("No value picks passed filters today (value + DQ + steam + gate2).")
        lines.append("Tracker: /tracker")
    else:
        for i, pick in enumerate(picks, start=1):
            lines.append(format_pick_line(pick, i))
            lines.append("")
        lines.append("Each-way paper picks logged to public SHA-256 ledger.")
    return "\n".join(lines).strip()
