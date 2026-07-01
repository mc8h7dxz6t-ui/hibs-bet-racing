from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from hibs_racing.config import load_config
from hibs_racing.place.paper_ledger import ledger_stats, load_ledger_rows, settle_paper_bets
from hibs_racing.cards.refresh import refresh_cards
from hibs_racing.cards.query import load_scored_cards
from hibs_racing.pick_explain import attach_pick_explanations


def _monitor_cfg() -> dict:
    return load_config().get("monitor", {})


def top_places_of_day(frame: pd.DataFrame | None = None, *, top_n: int | None = None) -> list[dict]:
    """
    Best place chances today — one top runner per race, ranked by model + combo.
    Filters tiny fields and weak combo priors.
    """
    cfg = _monitor_cfg()
    top_n = top_n or int(cfg.get("top_n", 12))
    min_field = int(cfg.get("min_field_size", 3))
    min_combo = float(cfg.get("min_combo_place", 0.35))
    min_place_prob = float(cfg.get("min_model_place_prob", 0.45))
    one_per_race = bool(cfg.get("one_per_race", True))

    if frame is None:
        frame = load_scored_cards()
    if frame.empty:
        return []

    work = frame.copy()
    work["field_size"] = pd.to_numeric(work.get("field_size"), errors="coerce")
    work["model_place_prob"] = pd.to_numeric(work.get("model_place_prob"), errors="coerce")
    work["combo_bayes_place"] = pd.to_numeric(work.get("combo_bayes_place"), errors="coerce")
    work = work[work["field_size"].fillna(0) >= min_field]
    work = work[work["model_place_prob"].fillna(0) >= min_place_prob]
    work = work[work["combo_bayes_place"].fillna(0) >= min_combo]
    if work.empty:
        return []

    work["place_score"] = work["model_place_prob"] * 0.65 + work["combo_bayes_place"] * 0.35
    work = work.sort_values(["race_id", "place_score"], ascending=[True, False])
    if one_per_race:
        work = work.groupby("race_id", sort=False).head(1)
    work = work.sort_values("place_score", ascending=False).head(top_n)

    picks: list[dict] = []
    for rank, (_, row) in enumerate(work.iterrows(), start=1):
        rec = row.to_dict()
        rec["day_rank"] = rank
        rec["place_score"] = float(row["place_score"])
        picks.append(rec)
    return attach_pick_explanations(picks, frame)


def monitor_snapshot(*, refresh: bool = False, settle: bool = True) -> dict:
    """Full monitor payload for UI / API auto-poll."""
    cfg = _monitor_cfg()
    refresh_error = None
    if refresh:
        try:
            refresh_cards(
                source=cfg.get("card_source", "racing_api"),
                region=cfg.get("default_region", "gb"),
                day=int(cfg.get("card_day", 1)),
                window_hours=int(cfg.get("window_hours", 24)),
            )
        except Exception as exc:
            refresh_error = str(exc)

    settle_stats = settle_paper_bets() if settle else {}
    frame = load_scored_cards()
    card_date = frame["card_date"].iloc[0] if not frame.empty else None
    picks = top_places_of_day(frame)
    from hibs_racing.utils.monetization import attach_monetized_links

    picks = attach_monetized_links(picks)

    return {
        "updated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "card_date": card_date,
        "top_places": picks,
        "top_count": len(picks),
        "runner_count": len(frame),
        "race_count": int(frame["race_id"].nunique()) if not frame.empty else 0,
        "ledger": ledger_stats().to_dict(),
        "recent_ledger": load_ledger_rows(limit=12, backtest=False),
        "settle": settle_stats,
        "refresh_error": refresh_error,
        "poll_seconds": int(cfg.get("auto_refresh_seconds", 300)),
    }


def run_monitor_cycle(*, refresh: bool = False) -> dict:
    return monitor_snapshot(refresh=refresh, settle=True)
