"""Production sniper lane — Gate7 true-sniper overlay on value_flag runners."""

from __future__ import annotations

from typing import Any

import pandas as pd

from hibs_racing.cards.actionability import value_gate_reason
from hibs_racing.cards.ui_frame import gate_reason_is_clear, is_value_pick, safe_value_mask
from hibs_racing.config import load_config
from hibs_racing.pick_explain import attach_pick_explanations


def sniper_lane_paper_cfg() -> dict[str, Any]:
    """Gate7 true-sniper thresholds from ingest config (replay-aligned)."""
    from hibs_racing.backtest.gate_impact import gate7_config

    full = load_config()
    paper = dict(full.get("paper") or {})
    return gate7_config(paper, full)


def passes_sniper_lane_row(row: pd.Series | dict, *, paper_cfg: dict[str, Any] | None = None) -> bool:
    """True when a value_flag runner also clears Gate7 sniper gates."""
    cfg = paper_cfg or sniper_lane_paper_cfg()
    if isinstance(row, dict):
        row = pd.Series(row)
    if not is_value_pick(row.get("value_flag")):
        return False
    if not gate_reason_is_clear(row.get("value_gate_reason")):
        return False
    return value_gate_reason(row, cfg) is None


def top_sniper_lane_picks(frame: pd.DataFrame | None = None, *, top_n: int | None = None) -> list[dict]:
    """
    Sniper-lane runners — value_flag + Gate7 (OR/RTF/confidence/stressed EV), capped 1/race & 1/meeting.
  Ranked by each-way EV.
    """
    cfg = load_config()
    monitor = cfg.get("monitor", {}) or {}
    top_n = top_n or int(monitor.get("sniper_lane_top_n", 6))
    sniper_cfg = sniper_lane_paper_cfg()
    g2 = sniper_cfg.get("gate2") or {}
    max_per_race = int(g2.get("max_value_per_race", 1) or 1)
    max_per_meeting = int(g2.get("max_value_per_meeting", 1) or 1)

    if frame is None:
        from hibs_racing.cards.query import load_scored_cards

        frame = load_scored_cards()
    if frame.empty:
        return []

    work = frame[safe_value_mask(frame)].copy()
    if work.empty:
        return []

    mask = work.apply(lambda row: passes_sniper_lane_row(row, paper_cfg=sniper_cfg), axis=1)
    work = work[mask]
    if work.empty:
        return []

    work["ew_combined_ev"] = pd.to_numeric(work.get("ew_combined_ev"), errors="coerce")
    work = work.sort_values(["race_id", "ew_combined_ev"], ascending=[True, False], na_position="last")
    if max_per_race > 0:
        work = work.groupby("race_id", sort=False).head(max_per_race)
    if max_per_meeting > 0 and "meeting_id" in work.columns:
        work = work.sort_values(["meeting_id", "ew_combined_ev"], ascending=[True, False], na_position="last")
        work = work.groupby("meeting_id", sort=False).head(max_per_meeting)
    work = work.sort_values("ew_combined_ev", ascending=False, na_position="last").head(top_n)

    picks: list[dict] = []
    for rank, (_, row) in enumerate(work.iterrows(), start=1):
        rec = row.to_dict()
        rec["day_rank"] = rank
        rec["sniper_lane_rank"] = rank
        rec["lane"] = "sniper"
        picks.append(rec)
    return attach_pick_explanations(picks, frame)
