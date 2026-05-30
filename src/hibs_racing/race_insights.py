from __future__ import annotations

import math

import pandas as pd

from hibs_racing.pick_explain import explain_pick


def _f(value: object, default: float = 0.0) -> float:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def build_race_insights(race_df: pd.DataFrame) -> dict:
    """Race-level summary for UI: top picks, value angles, field notes."""
    if race_df.empty:
        return {}

    frame = race_df.copy()
    frame["model_place_prob"] = pd.to_numeric(frame.get("model_place_prob"), errors="coerce").fillna(0)
    frame = frame.sort_values("model_place_prob", ascending=False)
    first = frame.iloc[0]
    value_rows = frame[frame.get("value_flag", 0) == 1] if "value_flag" in frame.columns else frame.iloc[0:0]

    top_picks: list[dict] = []
    for _, row in frame.head(3).iterrows():
        explained = explain_pick(row, race_peers=frame)
        top_picks.append(
            {
                "horse_name": row.get("horse_name"),
                "model_place_prob": _f(row.get("model_place_prob")),
                "combo_bayes_place": _f(row.get("combo_bayes_place")),
                "value_flag": int(_f(row.get("value_flag"))),
                "pick_summary": explained.get("pick_summary"),
                "pick_reasons": explained.get("pick_reasons", [])[:3],
            }
        )

    bullets: list[str] = []
    top = top_picks[0] if top_picks else None
    if top and top["model_place_prob"] >= 0.50:
        bullets.append(
            f"{top['horse_name']} leads the place model at {top['model_place_prob'] * 100:.0f}% "
            f"(combo prior {top['combo_bayes_place']:.2f})."
        )
    elif top:
        bullets.append(
            f"Open-looking {int(frame['model_place_prob'].max() * 100)}% top place estimate — "
            f"{top['horse_name']} edges the field on blended signals."
        )

    if len(value_rows):
        names = ", ".join(value_rows["horse_name"].astype(str).head(3).tolist())
        bullets.append(f"{len(value_rows)} value flag(s): {names} pass EW place EV gates.")

    combo = pd.to_numeric(frame.get("combo_bayes_place"), errors="coerce")
    if combo.notna().any():
        spread = float(combo.max() - combo.min())
        if spread >= 0.15:
            bullets.append(
                f"Wide combo spread ({spread:.2f}) — jockey/trainer priors separate this field clearly."
            )

    hidden = pd.to_numeric(frame.get("hidden_potential"), errors="coerce")
    if hidden.notna().any() and float(hidden.max()) > 10:
        leader = frame.loc[hidden.idxmax()]
        bullets.append(
            f"Hidden-potential angle on {leader.get('horse_name')} "
            f"(score {float(hidden.max()):.1f}) — comments vs OR mismatch."
        )

    field = int(_f(first.get("field_size"))) or len(frame)
    if field <= 6:
        bullets.append(f"Small {field}-runner field — place pool less diluted.")
    elif field >= 14:
        bullets.append(f"Deep {field}-runner handicap — place % compressed; combo/NLP rank matters.")

    if not bullets:
        bullets.append("Standard place profile — rank by model place % and combo prior.")

    return {
        "top_pick": top_picks[0] if top_picks else None,
        "top_picks": top_picks,
        "value_count": len(value_rows),
        "field_size": field,
        "max_place_prob": float(frame["model_place_prob"].max()),
        "bullets": bullets[:5],
        "race_name": first.get("race_name"),
        "off_time": first.get("off_time"),
        "race_class": first.get("race_class"),
        "going": first.get("going"),
    }
