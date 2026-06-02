from __future__ import annotations

import re

import pandas as pd

_UNRATED_RACE_RE = re.compile(
    r"\b(maiden|novices?|nursery|seller|introductory|amateur|conditional\s+jockeys)\b",
    re.I,
)


def is_exempt_unrated_race(row: pd.Series | dict) -> bool:
    """Maidens/novices etc. — no OR expected; rank-only for value/paper."""
    if isinstance(row, dict):
        row = pd.Series(row)
    name = str(row.get("race_name") or "")
    return bool(_UNRATED_RACE_RE.search(name))


def _official_rating(row: pd.Series | dict) -> float | None:
    if isinstance(row, dict):
        row = pd.Series(row)
    val = row.get("official_rating")
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _num(row: pd.Series | dict, key: str) -> float | None:
    if isinstance(row, dict):
        row = pd.Series(row)
    val = row.get(key)
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def cap_place_prob(prob: float, *, field_size: object) -> float:
    """Soft cap on Harville place prob — small fields were over-confident in live cards."""
    try:
        fs = int(float(field_size))
    except (TypeError, ValueError):
        fs = 12
    if fs <= 5:
        cap = 0.85
    elif fs <= 8:
        cap = 0.92
    else:
        cap = 0.97
    return min(float(prob), cap)


def _suitability_gate_reason(row: pd.Series | dict, paper_cfg: dict) -> str | None:
    """RP enrich suitability — block-only value flags when card stats show poor fit."""
    if not paper_cfg.get("suitability_gates_enabled", True):
        return None
    if isinstance(row, dict):
        row = pd.Series(row)

    min_dist_runs = int(paper_cfg.get("min_horse_dist_runs", 3))
    if paper_cfg.get("block_zero_dist_wins", True):
        dist_runs = _num(row, "horse_distance_runs")
        dist_wins = _num(row, "horse_distance_wins")
        trip = _num(row, "form_trip_change_f")
        max_trip = float(paper_cfg.get("max_trip_change_f", 2.0))
        if (
            dist_runs is not None
            and dist_wins is not None
            and dist_runs >= min_dist_runs
            and dist_wins == 0
            and trip is not None
            and trip >= max_trip
        ):
            return "poor_distance_record"

    min_rtf = paper_cfg.get("min_trainer_rtf")
    if min_rtf is not None:
        rtf = _num(row, "trainer_rtf")
        if rtf is not None and rtf < float(min_rtf):
            return "cold_trainer"

    poor = _num(row, "form_poor_runs_3")
    max_poor = paper_cfg.get("max_form_poor_runs_3")
    if max_poor is not None and poor is not None and poor >= float(max_poor):
        return "poor_recent_form"

    return None


def _gate2_regime_thresholds(field_size: object, paper_cfg: dict) -> tuple[float, float]:
    fs = _num({"field_size": field_size}, "field_size")
    gate2 = paper_cfg.get("gate2", {}) if isinstance(paper_cfg.get("gate2"), dict) else {}
    small_max = int(gate2.get("small_field_max", 7))
    large_min = int(gate2.get("large_field_min", 12))
    if fs is None:
        return float(gate2.get("min_place_ev_medium", paper_cfg.get("min_place_ev", 0.05))), float(
            gate2.get("min_combo_medium", paper_cfg.get("min_combo_bayes_place", 0.22))
        )
    if fs <= small_max:
        return float(gate2.get("min_place_ev_small", max(0.02, float(paper_cfg.get("min_place_ev", 0.05)) - 0.01))), float(
            gate2.get("min_combo_small", max(0.18, float(paper_cfg.get("min_combo_bayes_place", 0.22)) - 0.02))
        )
    if fs >= large_min:
        return float(gate2.get("min_place_ev_large", float(paper_cfg.get("min_place_ev", 0.05)) + 0.02)), float(
            gate2.get("min_combo_large", float(paper_cfg.get("min_combo_bayes_place", 0.22)) + 0.03)
        )
    return float(gate2.get("min_place_ev_medium", paper_cfg.get("min_place_ev", 0.05))), float(
        gate2.get("min_combo_medium", paper_cfg.get("min_combo_bayes_place", 0.22))
    )


def _gate2_confidence(row: pd.Series | dict, paper_cfg: dict) -> float:
    gate2 = paper_cfg.get("gate2", {}) if isinstance(paper_cfg.get("gate2"), dict) else {}
    keys = list(
        gate2.get(
            "confidence_keys",
            [
                "official_rating",
                "model_place_prob",
                "combo_bayes_place",
                "ew_combined_ev",
                "win_decimal",
                "trainer_rtf",
            ],
        )
    )
    if isinstance(row, dict):
        row = pd.Series(row)
    seen = 0
    ok = 0
    for key in keys:
        seen += 1
        val = row.get(key)
        if val is None:
            continue
        if isinstance(val, float) and pd.isna(val):
            continue
        if isinstance(val, str) and not val.strip():
            continue
        ok += 1
    return (ok / seen) if seen else 0.0


def _gate2_reason(row: pd.Series | dict, paper_cfg: dict) -> str | None:
    gate2 = paper_cfg.get("gate2", {}) if isinstance(paper_cfg.get("gate2"), dict) else {}
    if not gate2.get("enabled", False):
        return None
    if isinstance(row, dict):
        row = pd.Series(row)

    min_conf = float(gate2.get("min_confidence", 0.55))
    conf = _gate2_confidence(row, paper_cfg)
    if conf < min_conf:
        return "gate2_low_confidence"

    place_ev = _num(row, "place_ev")
    combo = _num(row, "combo_bayes_place")
    min_ev, min_combo = _gate2_regime_thresholds(row.get("field_size"), paper_cfg)
    if place_ev is not None and place_ev < min_ev:
        return "gate2_regime_ev"
    if combo is not None and combo < min_combo:
        return "gate2_regime_combo"

    # Robustness check: implied edge should survive small odds deterioration.
    shock = float(gate2.get("price_shock_per_decimal", 0.01))
    win_dec = _num(row, "win_decimal")
    if place_ev is not None and win_dec is not None:
        stressed_ev = place_ev - max(0.0, win_dec - 1.0) * shock
        if stressed_ev < float(gate2.get("min_stressed_place_ev", 0.0)):
            return "gate2_price_fragile"
    return None


def value_gate_reason(row: pd.Series | dict, paper_cfg: dict) -> str | None:
    """
    Return None if row may keep value_flag=1; else a stable reason code.
    Scoring is unchanged — this only gates paper/value actionability.
    """
    if isinstance(row, dict):
        row = pd.Series(row)
    if not paper_cfg.get("value_gates_enabled", True):
        return None

    if paper_cfg.get("exempt_unrated_races", True) and is_exempt_unrated_race(row):
        return "unrated_race_expected"

    or_val = _official_rating(row)
    if paper_cfg.get("require_official_rating_for_value", True) and or_val is None:
        return "missing_or"

    min_or = paper_cfg.get("min_official_rating")
    if min_or is not None and or_val is not None and or_val < float(min_or):
        return "below_or_floor"

    suit = _suitability_gate_reason(row, paper_cfg)
    if suit:
        return suit

    gate2 = _gate2_reason(row, paper_cfg)
    if gate2:
        return gate2

    return None


def apply_value_gates(frame: pd.DataFrame, paper_cfg: dict | None = None) -> pd.DataFrame:
    """Clear value_flag where actionability gates fail; set value_gate_reason on blocked rows."""
    if frame.empty:
        return frame
    cfg = paper_cfg or {}
    out = frame.copy()
    reasons: list[str | None] = []
    for _, row in out.iterrows():
        if int(row.get("value_flag") or 0) != 1:
            reasons.append(None)
            continue
        reason = value_gate_reason(row, cfg)
        reasons.append(reason)
    out["value_gate_reason"] = reasons
    blocked = out["value_gate_reason"].notna()
    out.loc[blocked, "value_flag"] = 0

    gate2 = cfg.get("gate2", {}) if isinstance(cfg.get("gate2"), dict) else {}
    if gate2.get("enabled", False):
        # Optional portfolio concentration controls.
        per_race_cap = gate2.get("max_value_per_race")
        if per_race_cap is not None and "race_id" in out.columns:
            keep_idx = (
                out[out["value_flag"] == 1]
                .sort_values(["race_id", "ew_combined_ev"], ascending=[True, False], na_position="last")
                .groupby("race_id", sort=False)
                .head(int(per_race_cap))
                .index
            )
            drop_idx = out[(out["value_flag"] == 1) & (~out.index.isin(keep_idx))].index
            if len(drop_idx):
                out.loc[drop_idx, "value_flag"] = 0
                out.loc[drop_idx, "value_gate_reason"] = "gate2_race_cap"

        per_meeting_cap = gate2.get("max_value_per_meeting")
        if per_meeting_cap is not None and {"card_date", "course"}.issubset(out.columns):
            keep_idx = (
                out[out["value_flag"] == 1]
                .sort_values(["card_date", "course", "ew_combined_ev"], ascending=[True, True, False], na_position="last")
                .groupby(["card_date", "course"], sort=False)
                .head(int(per_meeting_cap))
                .index
            )
            drop_idx = out[(out["value_flag"] == 1) & (~out.index.isin(keep_idx))].index
            if len(drop_idx):
                out.loc[drop_idx, "value_flag"] = 0
                out.loc[drop_idx, "value_gate_reason"] = "gate2_meeting_cap"
    return out
