from __future__ import annotations

import math

import pandas as pd


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


def explain_pick(row: dict | pd.Series, *, race_peers: pd.DataFrame | None = None) -> dict[str, object]:
    """Plain-English bullets for why this runner ranks as a place angle."""
    if isinstance(row, pd.Series):
        row = row.to_dict()

    jockey = (row.get("jockey") or "Jockey").strip()
    trainer = (row.get("trainer") or "Trainer").strip()
    combo = _f(row.get("combo_bayes_place"))
    jockey_place = _f(row.get("jockey_bayes_place"))
    trainer_place = _f(row.get("trainer_bayes_place"))
    jockey_90 = _f(row.get("jockey_place_90d"))
    trainer_90 = _f(row.get("trainer_place_90d"))
    jockey_vs = _f(row.get("jockey_vs_field"))
    trainer_vs = _f(row.get("trainer_vs_field"))
    place_p = _f(row.get("model_place_prob"))
    hidden = _f(row.get("hidden_potential"), default=float("nan"))
    nlp_rank = _f(row.get("nlp_pace_rank"), default=float("nan"))
    field = _i(row.get("field_size"))
    or_val = _i(row.get("official_rating"))
    value_flag = int(_f(row.get("value_flag")))
    ew_ev = row.get("ew_combined_ev")
    raw_comment = row.get("card_comment")
    card_comment = raw_comment.strip() if isinstance(raw_comment, str) else ""

    reasons: list[str] = []

    if combo >= 0.55:
        reasons.append(
            f"{jockey} & {trainer} have a strong place record together "
            f"({combo * 100:.0f}% Bayesian top-3 rate from your ingested history)."
        )
    elif combo >= 0.40:
        reasons.append(
            f"Trainer–jockey combo rates above the field norm for places ({combo * 100:.0f}% prior)."
        )

    if jockey_place >= 0.45 and jockey_vs >= 0.05:
        reasons.append(
            f"{jockey} place rate {jockey_place * 100:.0f}% "
            f"({jockey_90 * 100:.0f}% last 90d) — above rivals in this race."
        )
    elif jockey_place >= 0.40:
        reasons.append(f"{jockey} carries a {jockey_place * 100:.0f}% historical place profile.")

    if trainer_place >= 0.45 and trainer_vs >= 0.05:
        reasons.append(
            f"{trainer} yard (trainer) place rate {trainer_place * 100:.0f}% "
            f"({trainer_90 * 100:.0f}% last 90d) — stronger than field median."
        )
    elif trainer_place >= 0.40:
        reasons.append(f"{trainer} stable profile {trainer_place * 100:.0f}% place prior.")

    if not math.isnan(nlp_rank):
        if nlp_rank <= 1.5:
            reasons.append(
                "Top sectional pace score in this race — last-run comments flagged strong late/finish speed."
            )
        elif nlp_rank <= 3.0:
            reasons.append(
                f"Pace profile ranks #{nlp_rank:.0f} in the race on NLP sectional tags."
            )

    if not math.isnan(hidden) and hidden > 8:
        reasons.append(
            "Hidden-potential signal: running comments suggest more ability than the official rating implies."
        )

    if race_peers is not None and not race_peers.empty and or_val is not None:
        peer_or = pd.to_numeric(race_peers["official_rating"], errors="coerce")
        if peer_or.notna().any():
            avg_or = float(peer_or.mean())
            if or_val <= avg_or - 4:
                reasons.append(
                    f"OR {or_val} is {avg_or - or_val:.0f}lb below the field average — place chance driven by form, not the mark."
                )
            elif or_val >= avg_or + 4:
                reasons.append(
                    f"Top-rated on OR ({or_val}) vs rivals — model still likes the place profile on combo/pace mix."
                )

    if place_p >= 0.55:
        reasons.append(
            f"Harville place model: {place_p * 100:.0f}% chance of top-3 after blending combo, pace and relative ratings."
        )
    elif place_p >= 0.45:
        fs = f"{field}-runner" if field else "this"
        reasons.append(
            f"Estimated {place_p * 100:.0f}% place probability in a {fs} race — enough to lead today's shortlist."
        )

    if value_flag == 1:
        reasons.append("Passes value gates: positive each-way place expected value at logged odds.")
    elif ew_ev is not None and not (isinstance(ew_ev, float) and math.isnan(ew_ev)) and _f(ew_ev) > 0.05:
        reasons.append(f"Each-way EV +{_f(ew_ev):.2f} units vs offered price (if odds loaded).")

    if card_comment and len(card_comment) > 20 and math.isnan(nlp_rank):
        snippet = card_comment[:80] + ("…" if len(card_comment) > 80 else "")
        reasons.append(f"Card spotlight: \"{snippet}\"")

    fit_rows = row.get("enrich_fit_rows") or []
    for item in fit_rows[:2]:
        label = item.get("label") or "Record"
        val = item.get("value") or ""
        if val:
            reasons.append(f"RP {label.lower()}: {val}.")
    trip = row.get("enrich_trip_label")
    if trip:
        reasons.append(trip + ".")
    for flag in row.get("enrich_flags") or []:
        if flag.get("label"):
            reasons.append(str(flag["label"]) + ".")

    if not reasons:
        reasons.append(
            "Selected as the strongest place blend of trainer–jockey prior and model place probability in this race."
        )

    return {
        "pick_summary": reasons[0],
        "pick_reasons": reasons,
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
