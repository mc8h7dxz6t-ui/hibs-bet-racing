"""Morning Smart Portfolio picks — Gate3-aligned digest with immutable snapshot."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.backtest.snapshot_store import scoring_config_hash
from hibs_racing.cards.lane_paper import attach_lane_flags
from hibs_racing.cards.query import load_scored_cards
from hibs_racing.cards.ui_frame import gate_reason_is_clear, is_value_pick
from hibs_racing.config import ROOT, load_config
from hibs_racing.pick_explain import attach_pick_explanations
from hibs_racing.web_service import dashboard_context, novice_pick_candidates

SNAPSHOT_DIR = ROOT / "data" / "smart_picks"


def _smart_picks_lane() -> str:
    cfg = load_config()
    lanes = cfg.get("paper_lanes") or {}
    return str(lanes.get("smart_picks_lane") or "gate3").strip().lower()


def _lane_flag_col(lane: str) -> str | None:
    if lane in ("production", "default"):
        return None
    return f"flag_{lane}" if lane.startswith("gate") else f"flag_{lane}"


def filter_smart_picks(candidates: list[dict[str, Any]], *, limit: int = 3) -> list[dict[str, Any]]:
    from hibs_racing.config import load_config

    paper = load_config().get("paper", {})
    raw_gates = paper.get("allowed_steam_gates", ["proceed", "scale_up", "unknown"])
    if isinstance(raw_gates, (list, tuple)):
        allowed_gates = {str(g).lower() for g in raw_gates}
    else:
        allowed_gates = {"proceed", "scale_up", "unknown"}
    min_dq = int(paper.get("min_data_quality_pct") or 75)
    lane = _smart_picks_lane()
    flag_col = _lane_flag_col(lane)

    filtered = [
        c
        for c in candidates
        if is_value_pick(c.get("value_flag"))
        and gate_reason_is_clear(c.get("value_gate_reason"))
        and int(c.get("data_quality_pct") or 0) >= min_dq
        and str(c.get("steam_gate") or "proceed").lower() in allowed_gates
        and (
            flag_col is None
            or int(c.get(flag_col) or c.get("lane_flag") or 0) == 1
        )
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


def _digest_hash(picks: list[dict[str, Any]], *, config_hash: str, lane: str) -> str:
    payload = json.dumps(
        {
            "lane": lane,
            "config_hash": config_hash,
            "picks": [
                {
                    "runner_id": p.get("runner_id"),
                    "horse_name": p.get("horse_name"),
                    "offered_win": p.get("win_decimal"),
                    "ew_combined_ev": p.get("ew_combined_ev"),
                }
                for p in picks
            ],
        },
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def persist_smart_picks_snapshot(payload: dict[str, Any]) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    card_date = payload.get("card_date") or datetime.now(timezone.utc).date().isoformat()
    path = SNAPSHOT_DIR / f"{card_date}.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    latest = SNAPSHOT_DIR / "latest.json"
    latest.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_smart_picks_snapshot(*, card_date: str | None = None) -> dict[str, Any] | None:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    path = SNAPSHOT_DIR / f"{card_date}.json" if card_date else SNAPSHOT_DIR / "latest.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_morning_smart_picks(*, limit: int = 3, window_hours: int = 24) -> dict[str, Any]:
    lane = _smart_picks_lane()
    ctx = dashboard_context(window_hours=window_hours)
    frame = load_scored_cards()
    if not frame.empty and lane != "production":
        frame = attach_lane_flags(frame)
        flag_col = _lane_flag_col(lane)
        if flag_col and flag_col in frame.columns:
            for m in ctx.get("meetings") or []:
                for race in m.get("races") or []:
                    for runner in race.get("runners") or []:
                        rid = str(runner.get("runner_id") or "")
                        if not rid:
                            continue
                        match = frame[frame["runner_id"].astype(str) == rid]
                        if not match.empty:
                            runner[flag_col] = int(match.iloc[0].get(flag_col) or 0)

    candidates = novice_pick_candidates(ctx.get("meetings") or [])
    picks = filter_smart_picks(candidates, limit=limit)
    return {
        "ok": True,
        "pick_count": len(picks),
        "picks": picks,
        "card_dates": ctx.get("card_dates") or [],
        "scoring_method": ctx.get("scoring_method"),
        "candidate_count": len(candidates),
        "lane": lane,
    }


def build_morning_smart_picks_explained(*, limit: int = 3, window_hours: int = 24) -> dict[str, Any]:
    """Same shortlist as build_morning_smart_picks plus pick_reasons + frozen snapshot."""
    base = build_morning_smart_picks(limit=limit, window_hours=window_hours)
    frame = load_scored_cards()
    merged = [_merge_pick_with_frame(p, frame) for p in base.get("picks") or []]
    for i, p in enumerate(merged, start=1):
        p["day_rank"] = i
    explained = attach_pick_explanations(merged, frame) if not frame.empty else merged
    cfg_hash = scoring_config_hash(load_config().get("paper", {}))
    lane = base.get("lane") or _smart_picks_lane()
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    card_date = (base.get("card_dates") or [None])[0]
    digest_hash = _digest_hash(explained, config_hash=cfg_hash, lane=lane)
    snapshot = {
        **base,
        "picks": explained,
        "generated_at": generated_at,
        "scoring_config_hash": cfg_hash,
        "digest_hash": digest_hash,
        "card_date": card_date,
        "frozen": True,
    }
    if explained:
        persist_smart_picks_snapshot(snapshot)
    return snapshot


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
    lane = payload.get("lane") or "gate3"
    lines = [
        f"🏇 {product_name} — Daily Value Sheet",
        f"Cards: {dates} · lane {lane}",
        "",
    ]
    if not picks:
        lines.append("No value picks passed filters today (value + DQ + steam + lane gate).")
    else:
        for i, pick in enumerate(picks, start=1):
            lines.append(format_pick_line(pick, i))
            lines.append("")
    digest = payload.get("digest_hash")
    if digest:
        lines.append(f"Digest: {digest[:16]}…")
    lines.append("Tracker: /tracker")
    return "\n".join(lines)
