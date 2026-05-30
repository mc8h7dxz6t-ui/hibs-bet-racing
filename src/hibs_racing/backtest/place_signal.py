from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db

TAG_COLUMNS = [
    "late_pace_acceleration",
    "finishing_burst",
    "stamina_deficit",
    "trouble_in_running",
    "prominent_early",
    "held_up",
    "sectional_composite",
    "late_pace_level",
    "finishing_burst_level",
]


@dataclass
class BacktestReport:
    train_rows: int
    test_rows: int
    baseline_place_rate: float
    tag_coverage_pct: float
    tag_lift_top_tag: str | None
    tag_lift_rate: float | None
    logistic_tag_auc: float | None
    message: str

    def to_dict(self) -> dict:
        return {
            "train_rows": self.train_rows,
            "test_rows": self.test_rows,
            "baseline_place_rate": round(self.baseline_place_rate, 4),
            "tag_coverage_pct": round(self.tag_coverage_pct, 2),
            "tag_lift_top_tag": self.tag_lift_top_tag,
            "tag_lift_rate": round(self.tag_lift_rate, 4) if self.tag_lift_rate is not None else None,
            "logistic_tag_auc": round(self.logistic_tag_auc, 4) if self.logistic_tag_auc is not None else None,
            "message": self.message,
        }


def _sigmoid(x: float) -> float:
    if x >= 0:
        z = math.exp(-x)
        return 1.0 / (1.0 + z)
    z = math.exp(x)
    return z / (1.0 + z)


def _train_logistic(
    rows: list[dict],
    feature_keys: list[str],
    *,
    lr: float = 0.08,
    epochs: int = 120,
) -> tuple[list[float], float]:
    weights = [0.0] * len(feature_keys)
    bias = 0.0
    for _ in range(epochs):
        for row in rows:
            x = [float(row.get(k) or 0) for k in feature_keys]
            y = float(row["next_placed"])
            logit = bias + sum(w * xi for w, xi in zip(weights, x))
            pred = _sigmoid(logit)
            err = pred - y
            bias -= lr * err
            for i, xi in enumerate(x):
                weights[i] -= lr * err * xi
    return weights, bias


def _auc(scores: list[float], labels: list[int]) -> float:
    pairs = sorted(zip(scores, labels), key=lambda p: p[0])
    n_pos = sum(labels)
    n_neg = len(labels) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    rank_sum = 0.0
    for rank, (_, label) in enumerate(pairs, start=1):
        if label == 1:
            rank_sum += rank
    u = rank_sum - n_pos * (n_pos + 1) / 2
    return u / (n_pos * n_neg)


def run_place_backtest(
    database: Path | None = None,
    *,
    config_path: Path | None = None,
) -> BacktestReport:
    """
    Out-of-time place/top-N check: do pace tags beat a constant base rate?
    Phase A success = positive lift on held-out dates + >=90% tag coverage.
    """
    cfg = load_config(config_path)
    db = database or db_path(cfg)
    init_db(db)

    train_end = cfg["backtest"]["train_end"]
    test_start = cfg["backtest"]["test_start"]

    query = """
        SELECT
            o.next_placed,
            o.next_race_date,
            t.late_pace_acceleration,
            t.finishing_burst,
            t.stamina_deficit,
            t.trouble_in_running,
            t.prominent_early,
            t.held_up,
            t.sectional_composite,
            t.late_pace_level,
            t.finishing_burst_level,
            t.tag_count
        FROM next_run_outcomes o
        JOIN comment_tags t ON t.runner_id = o.runner_id
        WHERE o.next_placed IS NOT NULL
    """

    with connect(db) as conn:
        rows = [dict(r) for r in conn.execute(query).fetchall()]

    if not rows:
        return BacktestReport(
            0,
            0,
            0.0,
            0.0,
            None,
            None,
            None,
            "No labelled rows — run ingest, build-tags, build-outcomes first.",
        )

    train = [r for r in rows if r["next_race_date"] <= train_end]
    test = [r for r in rows if r["next_race_date"] >= test_start]

    if not train or not test:
        return BacktestReport(
            len(train),
            len(test),
            0.0,
            0.0,
            None,
            None,
            None,
            "Adjust train_end / test_start in ingest/config.yaml for your date range.",
        )

    baseline = sum(r["next_placed"] for r in test) / len(test)
    coverage = sum(1 for r in test if (r["tag_count"] or 0) > 0) / len(test) * 100

    best_tag = None
    best_lift = None
    for tag in TAG_COLUMNS:
        active = [r for r in test if (r[tag] or 0) > 0]
        if len(active) < 20:
            continue
        rate = sum(r["next_placed"] for r in active) / len(active)
        lift = rate - baseline
        if best_lift is None or lift > best_lift:
            best_lift = lift
            best_tag = tag

    weights, bias = _train_logistic(train, TAG_COLUMNS)
    scores = []
    labels = []
    for row in test:
        x = [float(row.get(k) or 0) for k in TAG_COLUMNS]
        logit = bias + sum(w * xi for w, xi in zip(weights, x))
        scores.append(_sigmoid(logit))
        labels.append(int(row["next_placed"]))
    auc = _auc(scores, labels)

    msg = "Tags add signal" if best_lift and best_lift > 0.01 and auc > 0.52 else "No clear tag edge yet — tune lexicon or add data."
    return BacktestReport(
        train_rows=len(train),
        test_rows=len(test),
        baseline_place_rate=baseline,
        tag_coverage_pct=coverage,
        tag_lift_top_tag=best_tag,
        tag_lift_rate=best_lift,
        logistic_tag_auc=auc,
        message=msg,
    )
