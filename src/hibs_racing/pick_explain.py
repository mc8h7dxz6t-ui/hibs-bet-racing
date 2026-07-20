from __future__ import annotations

import math

import pandas as pd

from hibs_racing.web_format import fmt_prob_phrase, normalize_prob_pct


def _f(value: object, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _i(value: object) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _pct(value: object) -> float:
    return normalize_prob_pct(value) or 0.0


def explain_pick(row: dict | pd.Series, *, race_peers: pd.DataFrame | None = None) -> dict[str, object]:
    """Plain-English bullets for why this runner ranks as a place angle."""
    if isinstance(row, pd.Series):
        row = row.to_dict()

    jockey = (row.get("jockey") or "Jockey").strip()
    trainer = (row.get("trainer") or "Trainer").strip()
    combo = _pct(row.get("combo_bayes_place"))
    jockey_place = _pct(row.get("jockey_bayes_place"))
    trainer_place = _pct(row.get("trainer_bayes_place"))
    jockey_90 = _pct(row.get("jockey_place_90d"))
    trainer_90 = _pct(row.get("trainer_place_90d"))
    jockey_vs = _f(row.get("jockey_vs_field"))
    trainer_vs = _f(row.get("trainer_vs_field"))
    place_p = _pct(row.get("model_place_prob"))
    hidden = _f(row.get("hidden_potential"), default=float("nan"))
    nlp_rank = _f(row.get("nlp_pace_rank"), default=float("nan"))
    field = _i(row.get("field_size"))
    or_val = _i(row.get("official_rating"))
    value_flag = int(_f(row.get("value_flag")))
    ew_ev = row.get("ew_combined_ev")
    raw_comment = row.get("card_comment")
    card_comment = raw_comment.strip() if isinstance(raw_comment, str) else ""

    reasons: list[str] = []

    if combo >= 55:
        reasons.append(
            f"{jockey} & {trainer}: strong joint place record ({fmt_prob_phrase(combo)})."
        )
    elif combo >= 40:
        reasons.append(
            f"{jockey} & {trainer}: above-average combo place rate ({fmt_prob_phrase(combo)})."
        )

    if jockey_place >= 45 and jockey_vs >= 0.05:
        reasons.append(
            f"{jockey}: {fmt_prob_phrase(jockey_place)} place rate "
            f"({fmt_prob_phrase(jockey_90)} last 90d) — ahead of this field."
        )
    elif jockey_place >= 40:
        reasons.append(f"{jockey}: {fmt_prob_phrase(jockey_place)} historical place profile.")

    if trainer_place >= 45 and trainer_vs >= 0.05:
        reasons.append(
            f"{trainer}: {fmt_prob_phrase(trainer_place)} place rate "
            f"({fmt_prob_phrase(trainer_90)} last 90d) — stronger than field median."
        )
    elif trainer_place >= 40:
        reasons.append(f"{trainer}: {fmt_prob_phrase(trainer_place)} stable place profile.")

    if not math.isnan(nlp_rank):
        if nlp_rank <= 1.5:
            reasons.append("Top pace figure in the race on recent sectionals.")
        elif nlp_rank <= 3.0:
            reasons.append(f"Pace ranks #{nlp_rank:.0f} in this field.")

    if not math.isnan(hidden) and hidden > 8:
        reasons.append("Running comments suggest more ability than the official rating.")

    if race_peers is not None and not race_peers.empty and or_val is not None:
        peer_or = pd.to_numeric(race_peers["official_rating"], errors="coerce")
        if peer_or.notna().any():
            avg_or = float(peer_or.mean())
            if or_val <= avg_or - 4:
                reasons.append(
                    f"OR {or_val} is {avg_or - or_val:.0f}lb below the field average."
                )
            elif or_val >= avg_or + 4:
                reasons.append(f"Top OR ({or_val}) in the race.")

    if place_p >= 55:
        reasons.append(f"About a {fmt_prob_phrase(place_p)} chance of placing (top 3) from combo, pace and ratings.")
    elif place_p >= 45:
        fs = f"{field}-runner" if field else "this"
        reasons.append(f"Place chance about {fmt_prob_phrase(place_p)} in a {fs} race.")

    if value_flag == 1:
        reasons.append("Passes value gates at logged each-way odds.")
    elif ew_ev is not None and not (isinstance(ew_ev, float) and math.isnan(ew_ev)) and _f(ew_ev) > 0.05:
        reasons.append(f"Each-way EV +{_f(ew_ev):.2f} units at offered price.")

    if card_comment and len(card_comment) > 20 and math.isnan(nlp_rank):
        snippet = card_comment[:72] + ("…" if len(card_comment) > 72 else "")
        reasons.append(f"Card note: \"{snippet}\"")

    fit_rows = row.get("enrich_fit_rows") or []
    for item in fit_rows[:1]:
        label = item.get("label") or "Record"
        val = item.get("value") or ""
        if val:
            reasons.append(f"{label}: {val}.")
    trip = row.get("enrich_trip_label")
    if trip:
        reasons.append(trip + ".")
    for flag in (row.get("enrich_flags") or [])[:1]:
        if flag.get("label"):
            reasons.append(str(flag["label"]) + ".")

    if not reasons:
        reasons.append("Best place blend of combo prior and model probability in this race.")

    trimmed = reasons[:4]
    return {
        "pick_summary": trimmed[0],
        "pick_reasons": trimmed,
    }


def attach_pick_explanations(picks: list[dict], full_frame: pd.DataFrame) -> list[dict]:
    """Add pick_summary + pick_reasons to each ranked pick."""
    if not picks or full_frame.empty:
        return picks
    out: list[dict] = []
    for pick in picks:
        race_id = pick.get("race_id")
        peers = full_frame[full_frame["race_id"] == race_id] if race_id else None
        explained = {**pick, **explain_pick(pick, race_peers=peers)}
        place = explained.get("offered_place_decimal")
        if place is None or (isinstance(place, float) and pd.isna(place)):
            win = explained.get("win_decimal")
            if win is not None and not (isinstance(win, float) and pd.isna(win)):
                try:
                    win_f = float(win)
                    pf = float(explained.get("place_fraction") or 0.25)
                    if win_f > 1:
                        explained["offered_place_decimal"] = round(1.0 + (win_f - 1.0) * pf, 2)
                except (TypeError, ValueError):
                    pass
        out.append(explained)
    return out
