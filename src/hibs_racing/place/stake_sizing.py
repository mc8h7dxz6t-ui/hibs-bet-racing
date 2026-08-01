"""Kelly-based stake resolution — paper, shadow, and live execution parity."""

from __future__ import annotations

from typing import Any, Mapping, Optional

import pandas as pd

from hibs_racing.config import load_config


def paper_bankroll_units(cfg: dict | None = None) -> float:
    paper = (cfg or load_config()).get("paper") or {}
    try:
        return max(1.0, float(paper.get("bankroll_units", 100.0)))
    except (TypeError, ValueError):
        return 100.0


def resolve_stake_units(
    row: Mapping[str, Any],
    *,
    bankroll_units: float | None = None,
    default_stake: float | None = None,
    kelly_multiplier: float = 1.0,
    cfg: dict | None = None,
) -> float:
    """
    Stake from kelly_place_pct × bankroll × steam multiplier, else flat default.

    Industry standard: fractional Kelly already in kelly_place_pct; steam scales after base.
    """
    conf = cfg or load_config()
    paper = conf.get("paper") or {}
    br = bankroll_units if bankroll_units is not None else paper_bankroll_units(conf)
    fallback = default_stake if default_stake is not None else float(paper.get("default_stake", 1.0))

    kelly_pct = row.get("kelly_place_pct")
    base = fallback
    if kelly_pct is not None and not (isinstance(kelly_pct, float) and pd.isna(kelly_pct)):
        try:
            pct = float(kelly_pct)
            if pct > 0:
                base = br * pct / 100.0
        except (TypeError, ValueError):
            pass

    mult = max(0.0, float(kelly_multiplier or 1.0))
    return round(max(0.0, base * mult), 2)


def resolve_stakes_for_frame(
    frame: pd.DataFrame,
    *,
    bankroll_units: float | None = None,
    default_stake: float | None = None,
    gauge_by_runner: dict[str, Any] | None = None,
    cfg: dict | None = None,
) -> list[float]:
    gauges = gauge_by_runner or {}
    stakes: list[float] = []
    for rec in frame.to_dict(orient="records"):
        rid = str(rec.get("runner_id") or "")
        gauge = gauges.get(rid)
        mult = float(getattr(gauge, "kelly_multiplier", 1.0)) if gauge is not None else 1.0
        stakes.append(
            resolve_stake_units(
                rec,
                bankroll_units=bankroll_units,
                default_stake=default_stake,
                kelly_multiplier=mult,
                cfg=cfg,
            )
        )
    return stakes
