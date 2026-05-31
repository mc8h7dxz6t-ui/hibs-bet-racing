"""Morning Smart Portfolio picks — same filters as dashboard JS (novice UX)."""

from __future__ import annotations

from typing import Any

from hibs_racing.web_service import dashboard_context, novice_pick_candidates


def filter_smart_picks(candidates: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    allowed_gates = {"proceed", "scale_up"}
    filtered = [
        c
        for c in candidates
        if c.get("value_flag")
        and int(c.get("data_quality_pct") or 0) >= 75
        and str(c.get("steam_gate") or "proceed").lower() in allowed_gates
    ]
    filtered.sort(
        key=lambda c: float(c.get("place_score") or c.get("model_place_prob") or 0),
        reverse=True,
    )
    return filtered[: max(1, int(limit))]


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
        lines.append("No value picks passed filters today (value + DQ≥75% + steam gate).")
        lines.append("Tracker: /tracker")
    else:
        for i, pick in enumerate(picks, start=1):
            lines.append(format_pick_line(pick, i))
            lines.append("")
        lines.append("Each-way paper picks logged to public SHA-256 ledger.")
    return "\n".join(lines).strip()
