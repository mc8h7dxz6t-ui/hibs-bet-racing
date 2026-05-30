from __future__ import annotations

import pandas as pd

from hibs_racing.features.combo_stats import parse_class_num


def hidden_potential_score(row: pd.Series) -> float:
    """
    Low official rating + strong NLP pace + class drop → disguised runner signal.
    Higher = more hidden upside vs public rating.
    """
    base_or = float(row.get("official_rating") or 0)
    burst = float(row.get("finishing_burst_level") or 0)
    pace = float(row.get("sectional_composite") or 0)
    class_num = parse_class_num(row.get("race_class"))
    hist_class = row.get("horse_avg_class")
    class_drop = 0.0
    if class_num is not None and hist_class is not None and not pd.isna(hist_class):
        class_drop = float(hist_class) - class_num

    return (burst * 10.0) + (pace * 20.0) + (class_drop * 5.0) - (base_or * 0.15)


def add_horse_class_history(frame: pd.DataFrame) -> pd.DataFrame:
    """Rolling mean class level for each horse (prior runs only)."""
    out = frame.copy()
    if "race_date" not in out.columns and "card_date" in out.columns:
        out["race_date"] = out["card_date"]
    if "horse_avg_class" in out.columns:
        return out
    out["class_num"] = out["race_class"].map(parse_class_num)
    sort_cols = [c for c in ("horse_id", "race_date", "race_id") if c in out.columns]
    out = out.sort_values(sort_cols)
    out["horse_avg_class"] = (
        out.groupby("horse_id", sort=False)["class_num"]
        .transform(lambda s: s.expanding().mean().shift(1))
    )
    return out


def add_discrepancy_features(frame: pd.DataFrame) -> pd.DataFrame:
    out = add_horse_class_history(frame)
    out["hidden_potential"] = out.apply(hidden_potential_score, axis=1)
    return out
