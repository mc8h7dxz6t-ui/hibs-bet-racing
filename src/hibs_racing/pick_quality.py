"""Runner pick-quality tiers for UI gate filtering — single source of truth."""

from __future__ import annotations

import math
from typing import Any

from hibs_racing.cards.actionability import value_gate_reason
from hibs_racing.cards.data_quality import runner_data_quality_pct
from hibs_racing.cards.ui_frame import gate_reason_is_clear, is_value_pick
from hibs_racing.config import load_config
from hibs_racing.daily.pick_display import passes_loose_pick, passes_strict_pick
from hibs_racing.sniper_lane import passes_sniper_lane_row, sniper_lane_paper_cfg

# Ordered strict → loose for display; filter uses explicit membership checks.
GATE_FILTER_MODES: tuple[dict[str, str], ...] = (
    {"id": "all", "label": "All runners", "hint": "Full racecard field"},
    {"id": "paper_ready", "label": "Paper-ready", "hint": "Value + data quality + steam gates (betting tier)"},
    {"id": "sniper", "label": "Sniper (Gate7)", "hint": "Ultra-selective OR≥65, RTF≥20, stressed EV"},
    {"id": "value_lane", "label": "Value lane", "hint": "Gated value with positive each-way EV"},
    {"id": "value", "label": "Value (gated)", "hint": "value_flag cleared actionability gates"},
    {"id": "watchlist", "label": "Watchlist+", "hint": "Data quality + steam OK (engine watchlist)"},
)

_VALID_MODES = {m["id"] for m in GATE_FILTER_MODES}
_DEFAULT_MODE = "all"


def normalize_gate_filter_mode(mode: str | None) -> str:
    raw = (mode or _DEFAULT_MODE).strip().lower()
    return raw if raw in _VALID_MODES else _DEFAULT_MODE


def _num(val: object) -> float | None:
    if val is None:
        return None
    if isinstance(val, float) and math.isnan(val):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def runner_to_pick_context(runner: dict[str, Any]) -> dict[str, Any]:
    """Build pick-display dict from a racecard runner row (post market_gauge attach)."""
    gauge = runner.get("market_gauge") or {}
    ctx = dict(runner)
    ctx["data_quality_pct"] = runner_data_quality_pct(runner)
    ctx["steam_gate"] = str(gauge.get("gate") or runner.get("steam_gate") or "proceed")
    return ctx


def passes_value_lane_row(row: dict[str, Any], *, paper_cfg: dict[str, Any] | None = None) -> bool:
    """Value-lane pool row — same gates as monitor.top_value_lane_picks without top-N cap."""
    cfg = paper_cfg or (load_config().get("monitor") or {})
    if not is_value_pick(row.get("value_flag")):
        return False
    if not gate_reason_is_clear(row.get("value_gate_reason")):
        return False
    ev = _num(row.get("ew_combined_ev"))
    if ev is None or ev <= 0:
        return False
    min_field = int(cfg.get("min_field_size", 3) or 3)
    fs = _num(row.get("field_size"))
    if fs is not None and fs < min_field:
        return False
    return True


def passes_gated_value_row(row: dict[str, Any], *, paper_cfg: dict[str, Any] | None = None) -> bool:
    """Actionable value — value_flag plus live value_gate_reason check."""
    full = load_config()
    paper = paper_cfg or full.get("paper") or {}
    if not is_value_pick(row.get("value_flag")):
        return False
    if not gate_reason_is_clear(row.get("value_gate_reason")):
        return False
    return value_gate_reason(row, paper) is None


def classify_runner_pick_quality(runner: dict[str, Any]) -> dict[str, Any]:
    """Return boolean gate flags and highest qualifying tier for a runner."""
    ctx = runner_to_pick_context(runner)
    paper_cfg = load_config().get("paper") or {}
    sniper_cfg = sniper_lane_paper_cfg()

    flags = {
        "watchlist": passes_loose_pick(ctx, paper_cfg=paper_cfg),
        "value": passes_gated_value_row(ctx, paper_cfg=paper_cfg),
        "value_lane": passes_value_lane_row(ctx),
        "paper_ready": passes_strict_pick(ctx, paper_cfg=paper_cfg),
        "sniper": passes_sniper_lane_row(ctx, paper_cfg=sniper_cfg),
    }

    tier = "none"
    for candidate in ("sniper", "paper_ready", "value_lane", "value", "watchlist"):
        if flags[candidate]:
            tier = candidate
            break

    return {
        "pick_gate_tier": tier,
        "pick_gate_watchlist": flags["watchlist"],
        "pick_gate_value": flags["value"],
        "pick_gate_value_lane": flags["value_lane"],
        "pick_gate_paper_ready": flags["paper_ready"],
        "pick_gate_sniper": flags["sniper"],
        "data_quality_pct": int(ctx.get("data_quality_pct") or 0),
    }


def runner_passes_gate_filter(runner: dict[str, Any], mode: str) -> bool:
    mode = normalize_gate_filter_mode(mode)
    if mode == "all":
        return True
    quality = classify_runner_pick_quality(runner)
    key = {
        "watchlist": "pick_gate_watchlist",
        "value": "pick_gate_value",
        "value_lane": "pick_gate_value_lane",
        "paper_ready": "pick_gate_paper_ready",
        "sniper": "pick_gate_sniper",
    }.get(mode)
    return bool(key and quality.get(key))


def attach_pick_quality_flags(meetings: list[dict]) -> None:
    """Annotate every runner with pick_gate_* fields for template + client filter."""
    for meeting in meetings:
        for race in meeting.get("races") or []:
            for runner in race.get("runners") or []:
                runner.update(classify_runner_pick_quality(runner))


def gate_filter_modes() -> list[dict[str, str]]:
    return [dict(m) for m in GATE_FILTER_MODES]
