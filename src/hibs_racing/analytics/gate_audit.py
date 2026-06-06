"""Gate coverage audit — detect whether backtests were starved of genuine feature inputs."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

import pandas as pd

from hibs_racing.backtest.gate_impact import (
    WALKFORWARD_FOCUS_LANES,
    gate3_config,
    gate4_config,
    gate5_config,
    gate6_config,
    gate7_config,
)
from hibs_racing.backtest.snapshot_store import _expand_gates_json, load_snapshots, resolve_snapshot_config_hash
from hibs_racing.cards.actionability import _gate2_confidence
from hibs_racing.config import db_path, load_config
from hibs_racing.features.runner_enrich_backfill import coverage_report

logger = logging.getLogger(__name__)

# Institutional rule: NULL/NaN = unpopulated. Zero is valid for counters; not for RTF/rates.
_MISSING_FN: dict[str, Callable[[pd.Series], pd.Series]] = {
    "trainer_rtf": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "official_rating": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "win_decimal": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "place_ev": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "combo_bayes_place": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "model_place_prob": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "ew_combined_ev": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "horse_distance_runs": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "horse_distance_wins": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "form_trip_change_f": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "form_poor_runs_3": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "horse_course_win_rate": lambda s: pd.to_numeric(s, errors="coerce").isna(),
    "enrich_source": lambda s: s.isna() | (s.astype(str).str.strip() == ""),
}

LANE_CONFIG_BUILDERS = {
    "gate2": lambda paper, full: paper,
    "gate3": gate3_config,
    "gate4": gate4_config,
    "gate5": gate5_config,
    "gate6": gate6_config,
    "gate7": gate7_config,
    "gate8": gate3_config,
}

RUNNER_LANE_REQUIRED_FEATURES: dict[str, tuple[str, ...]] = {
    "gate3": ("official_rating", "trainer_rtf", "horse_course_win_rate"),
    "gate5": ("official_rating", "trainer_rtf"),
    "gate6": ("official_rating", "trainer_rtf"),
    "gate7": ("official_rating", "trainer_rtf"),
    "gate8": ("official_rating", "trainer_rtf"),
    "gate2": ("official_rating", "trainer_rtf"),
}

LANE_REQUIRED_FEATURES: dict[str, tuple[str, ...]] = {
    "gate2": (
        "official_rating",
        "win_decimal",
        "place_ev",
        "combo_bayes_place",
        "model_place_prob",
    ),
    "gate3": (
        "official_rating",
        "trainer_rtf",
        "win_decimal",
        "place_ev",
        "combo_bayes_place",
        "model_place_prob",
    ),
    "gate5": (
        "official_rating",
        "trainer_rtf",
        "win_decimal",
        "place_ev",
        "combo_bayes_place",
    ),
    "gate6": (
        "official_rating",
        "trainer_rtf",
        "win_decimal",
        "place_ev",
        "combo_bayes_place",
    ),
    "gate7": (
        "official_rating",
        "trainer_rtf",
        "win_decimal",
        "place_ev",
        "combo_bayes_place",
    ),
    "gate8": (
        "official_rating",
        "trainer_rtf",
        "win_decimal",
        "place_ev",
        "combo_bayes_place",
    ),
}


@dataclass
class FeatureCoverageRow:
    column: str
    present_pct: float
    missing_count: int
    total: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "column": self.column,
            "present_pct": round(self.present_pct, 2),
            "missing_count": self.missing_count,
            "total": self.total,
        }


@dataclass
class GateLaneAudit:
    lane: str
    total_runners: int
    genuine_rows: int
    data_density_pct: float
    min_trainer_rtf: float | None
    trainer_rtf_present_pct: float
    cold_trainer_would_block: int
    cold_trainer_skipped_null_rtf: int
    gate2_low_confidence_sim: int
    passed: bool
    verdict: str
    feature_rows: list[FeatureCoverageRow] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "lane": self.lane,
            "total_runners": self.total_runners,
            "genuine_rows": self.genuine_rows,
            "data_density_pct": round(self.data_density_pct, 2),
            "min_trainer_rtf": self.min_trainer_rtf,
            "trainer_rtf_present_pct": round(self.trainer_rtf_present_pct, 2),
            "cold_trainer_would_block": self.cold_trainer_would_block,
            "cold_trainer_skipped_null_rtf": self.cold_trainer_skipped_null_rtf,
            "gate2_low_confidence_sim": self.gate2_low_confidence_sim,
            "passed": self.passed,
            "verdict": self.verdict,
            "features": [r.to_dict() for r in self.feature_rows],
            "notes": self.notes,
        }


def _missing_mask(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series(True, index=frame.index)
    rule = _MISSING_FN.get(column)
    if rule:
        return rule(frame[column])
    series = frame[column]
    return series.isna() | (series.astype(str).str.strip() == "")


def feature_coverage_table(frame: pd.DataFrame, columns: tuple[str, ...]) -> list[FeatureCoverageRow]:
    total = len(frame)
    rows: list[FeatureCoverageRow] = []
    for col in columns:
        missing = int(_missing_mask(frame, col).sum()) if total else 0
        present_pct = 100.0 * (total - missing) / total if total else 0.0
        rows.append(FeatureCoverageRow(column=col, present_pct=present_pct, missing_count=missing, total=total))
    return rows


def _lane_paper_cfg(lane: str, paper_cfg: dict, full_cfg: dict) -> dict:
    builder = LANE_CONFIG_BUILDERS.get(lane)
    if builder is None:
        return paper_cfg
    if lane == "gate2":
        cfg = dict(paper_cfg)
        g2 = dict(cfg.get("gate2") or {})
        g2["enabled"] = True
        cfg["gate2"] = g2
        return cfg
    return builder(paper_cfg, full_cfg)


def audit_gate_lane(
    frame: pd.DataFrame,
    lane: str,
    *,
    paper_cfg: dict | None = None,
    full_cfg: dict | None = None,
    min_density_pct: float = 85.0,
    required_features: dict[str, tuple[str, ...]] | None = None,
) -> GateLaneAudit:
    """
    Measure whether a gate lane backtest had enough genuine inputs to be institutionally valid.

    Important: ``cold_trainer`` only blocks when trainer_rtf is present AND below threshold.
    Missing RTF is permissive (not a block) but reduces Gate2 confidence — both are reported.
    """
    full_cfg = full_cfg or load_config()
    paper_cfg = paper_cfg or full_cfg.get("paper", {})
    lane_cfg = _lane_paper_cfg(lane, paper_cfg, full_cfg)
    feat_map = required_features or LANE_REQUIRED_FEATURES
    required = feat_map.get(lane, feat_map.get("gate3", LANE_REQUIRED_FEATURES["gate3"]))
    total = len(frame)
    notes: list[str] = []

    if total == 0:
        return GateLaneAudit(
            lane=lane,
            total_runners=0,
            genuine_rows=0,
            data_density_pct=0.0,
            min_trainer_rtf=None,
            trainer_rtf_present_pct=0.0,
            cold_trainer_would_block=0,
            cold_trainer_skipped_null_rtf=0,
            gate2_low_confidence_sim=0,
            passed=False,
            verdict="no_data",
            notes=["empty frame"],
        )

    feat_rows = feature_coverage_table(frame, required)
    genuine_mask = pd.Series(True, index=frame.index)
    for col in required:
        genuine_mask &= ~_missing_mask(frame, col)
    genuine_rows = int(genuine_mask.sum())
    density = 100.0 * genuine_rows / total

    min_rtf = lane_cfg.get("min_trainer_rtf")
    min_rtf_f = float(min_rtf) if min_rtf is not None else None

    if "trainer_rtf" in frame.columns:
        rtf = pd.to_numeric(frame["trainer_rtf"], errors="coerce")
    else:
        rtf = pd.Series(float("nan"), index=frame.index)
    rtf_present = int(rtf.notna().sum())
    rtf_present_pct = 100.0 * rtf_present / total

    cold_block = 0
    cold_skip_null = 0
    if min_rtf_f is not None:
        null_rtf = rtf.isna()
        cold_skip_null = int(null_rtf.sum())
        cold_block = int((rtf.notna() & (rtf < min_rtf_f)).sum())
        if cold_skip_null > 0:
            notes.append(
                f"{cold_skip_null} runners ({100*cold_skip_null/total:.1f}%) had NULL trainer_rtf — "
                f"cold_trainer gate skipped (permissive), inflating pass volume vs dense-data replay."
            )

    g2_min_conf = float((lane_cfg.get("gate2") or {}).get("min_confidence", 0.55))
    low_conf = 0
    if (lane_cfg.get("gate2") or {}).get("enabled"):
        sample = frame.head(5000) if total > 5000 else frame
        for rec in sample.to_dict(orient="records"):
            conf = _gate2_confidence(rec, lane_cfg)
            if conf < g2_min_conf:
                low_conf += 1
        if total > 5000:
            low_conf = int(round(low_conf * total / len(sample)))
            notes.append(
                f"gate2_low_confidence_sim extrapolated from {len(sample)} / {total} runners."
            )

    passed = density >= min_density_pct
    if passed:
        verdict = "institutionally_valid"
    elif density >= 30.0:
        verdict = "partial_hindrance"
    else:
        verdict = "high_hindrance"

    if min_rtf_f is not None and rtf_present_pct < min_density_pct:
        notes.append(
            f"Lane requires trainer_rtf >= {min_rtf_f:.0f} but only {rtf_present_pct:.1f}% of rows "
            f"had populated RTF — sniper lanes cannot be fairly compared until RP backfill completes."
        )

    return GateLaneAudit(
        lane=lane,
        total_runners=total,
        genuine_rows=genuine_rows,
        data_density_pct=density,
        min_trainer_rtf=min_rtf_f,
        trainer_rtf_present_pct=rtf_present_pct,
        cold_trainer_would_block=cold_block,
        cold_trainer_skipped_null_rtf=cold_skip_null,
        gate2_low_confidence_sim=low_conf,
        passed=passed,
        verdict=verdict,
        feature_rows=feat_rows,
        notes=notes,
    )


def audit_gate_data_deprivation(
    frame: pd.DataFrame,
    gate_name: str,
    required_cols: list[str] | tuple[str, ...] | None = None,
    *,
    paper_cfg: dict | None = None,
    full_cfg: dict | None = None,
    min_density_pct: float = 85.0,
) -> GateLaneAudit:
    """Compatibility wrapper — prefer lane keys (gate3, gate5, …) over free-form column lists."""
    if required_cols:
        full_cfg = full_cfg or load_config()
        paper_cfg = paper_cfg or full_cfg.get("paper", {})
        lane_cfg = _lane_paper_cfg(gate_name, paper_cfg, full_cfg)
        audit = audit_gate_lane(frame, gate_name, paper_cfg=lane_cfg, full_cfg=full_cfg, min_density_pct=min_density_pct)
        # Override required set when caller passed explicit columns
        feat_rows = feature_coverage_table(frame, tuple(required_cols))
        genuine_mask = pd.Series(True, index=frame.index)
        for col in required_cols:
            genuine_mask &= ~_missing_mask(frame, col)
        genuine_rows = int(genuine_mask.sum())
        density = 100.0 * genuine_rows / len(frame) if len(frame) else 0.0
        audit.feature_rows = feat_rows
        audit.genuine_rows = genuine_rows
        audit.data_density_pct = density
        audit.passed = density >= min_density_pct
        audit.verdict = "institutionally_valid" if audit.passed else (
            "partial_hindrance" if density >= 30.0 else "high_hindrance"
        )
        return audit
    return audit_gate_lane(frame, gate_name, paper_cfg=paper_cfg, full_cfg=full_cfg, min_density_pct=min_density_pct)


def _enrich_source_breakdown(frame: pd.DataFrame) -> dict[str, Any]:
    if "enrich_source" not in frame.columns or frame.empty:
        return {"total": len(frame), "by_source": {}}
    counts = frame["enrich_source"].fillna("(null)").astype(str).value_counts().to_dict()
    return {"total": len(frame), "by_source": {str(k): int(v) for k, v in counts.items()}}


def _load_runners_window(db: Any, start: str, end: str) -> pd.DataFrame:
    from hibs_racing.features.store import connect, init_db

    cols = sorted(
        {
            "runner_id",
            "race_date",
            "official_rating",
            "trainer_rtf",
            "win_decimal",
            "place_ev",
            "combo_bayes_place",
            "model_place_prob",
            "ew_combined_ev",
            "horse_distance_runs",
            "horse_distance_wins",
            "form_trip_change_f",
            "form_poor_runs_3",
            "horse_course_win_rate",
            "enrich_source",
        }
    )
    init_db(db)
    with connect(db) as conn:
        existing = {row[1] for row in conn.execute("PRAGMA table_info(runners)").fetchall()}
        select_cols = [c for c in cols if c in existing]
        frame = pd.read_sql_query(
            f"""
            SELECT {", ".join(select_cols)}
            FROM runners
            WHERE finish_pos IS NOT NULL AND race_date >= ? AND race_date <= ?
            """,
            conn,
            params=(start, end),
        )
    if "race_date" in frame.columns:
        frame["card_date"] = frame["race_date"]
    return frame


def run_gate_coverage_audit(
    *,
    start: str | None = None,
    end: str | None = None,
    snapshot_config_hash: str | None = None,
    lanes: tuple[str, ...] | None = None,
    database: Any = None,
    min_density_pct: float | None = None,
    source: str = "both",
) -> dict[str, Any]:
    """Audit snapshot replay window for gate data deprivation (institutional++ pre-archive check)."""
    cfg = load_config()
    db = database or db_path(cfg)
    paper_cfg = cfg.get("paper", {})
    promo = cfg.get("experimental_replay_lanes", {}).get("promotion_criteria", {})
    if not isinstance(promo, dict):
        promo = {}
    density_floor = float(
        min_density_pct
        if min_density_pct is not None
        else promo.get("min_gate_data_density_pct", 85.0)
    )

    from hibs_racing.backtest.gate_benchmark import _historical_bounds

    max_start, max_end = _historical_bounds(db)
    start_s = start or max_start
    end_s = end or max_end
    if not start_s or not end_s:
        return {"error": "no historical settled data", "start": start_s, "end": end_s}

    audit_lanes = lanes or WALKFORWARD_FOCUS_LANES
    src = (source or "both").strip().lower()
    out: dict[str, Any] = {
        "start": start_s,
        "end": end_s,
        "min_density_pct": density_floor,
        "source": src,
        "runners_db_enrich": coverage_report(db, start=start_s, end=end_s),
    }

    snap_hash: str | None = None
    snapshot_block: dict[str, Any] | None = None
    runners_block: dict[str, Any] | None = None

    if src in ("snapshots", "both"):
        snap_hash = resolve_snapshot_config_hash(db, paper_cfg, explicit=snapshot_config_hash)
        snap = load_snapshots(db, start_s, end_s, config_hash=snap_hash)
        if snap.empty:
            snapshot_block = {
                "error": "no snapshots for window",
                "snapshot_config_hash": snap_hash,
            }
        else:
            frame = _expand_gates_json(snap)
            settled = frame[frame["finish_pos"].notna()].copy()
            lane_reports = [
                audit_gate_lane(
                    settled, lane, paper_cfg=paper_cfg, full_cfg=cfg,
                    min_density_pct=density_floor, required_features=LANE_REQUIRED_FEATURES,
                ).to_dict()
                for lane in audit_lanes
                if lane in LANE_REQUIRED_FEATURES
            ]
            snapshot_block = {
                "snapshot_config_hash": snap_hash,
                "settled_runners": len(settled),
                "enrich_source_breakdown": _enrich_source_breakdown(settled),
                "lanes": lane_reports,
                "retest_ready": all(
                    r.get("passed") for r in lane_reports if r.get("lane") in ("gate3", "gate5", "gate7")
                ),
            }

    if src in ("runners", "both"):
        runners = _load_runners_window(db, start_s, end_s)
        if runners.empty:
            runners_block = {"error": "no finished runners in window"}
        else:
            lane_reports = [
                audit_gate_lane(
                    runners, lane, paper_cfg=paper_cfg, full_cfg=cfg,
                    min_density_pct=density_floor, required_features=RUNNER_LANE_REQUIRED_FEATURES,
                ).to_dict()
                for lane in audit_lanes
                if lane in RUNNER_LANE_REQUIRED_FEATURES
            ]
            runners_block = {
                "finished_runners": len(runners),
                "enrich_source_breakdown": _enrich_source_breakdown(runners),
                "lanes": lane_reports,
                "retest_ready": all(
                    r.get("passed") for r in lane_reports if r.get("lane") in ("gate3", "gate5", "gate7")
                ),
            }

    if snapshot_block:
        out["snapshots"] = snapshot_block
    if runners_block:
        out["runners"] = runners_block
    if snap_hash:
        out["snapshot_config_hash"] = snap_hash

    retest_flags = [
        b.get("retest_ready")
        for b in (snapshot_block, runners_block)
        if isinstance(b, dict) and "retest_ready" in b
    ]
    out["retest_ready"] = bool(retest_flags) and all(retest_flags)

    if src == "snapshots" and snapshot_block and snapshot_block.get("error"):
        out["error"] = snapshot_block["error"]
    if src == "runners" and runners_block and runners_block.get("error"):
        out["error"] = runners_block["error"]

    out["gate_closure_note"] = (
        "Do not permanently archive Gate5/Gate7 until data_density >= "
        f"{density_floor:.0f}% on all sniper lanes and gate-impact walk-forward re-run."
    )
    out["gate3_paper_note"] = "Gate3 paper anchor: keep active on live cards as control benchmark."
    out["message"] = (
        "Gate coverage audit PASSED — window has dense inputs."
        if out.get("retest_ready")
        else "Gate coverage audit FAILED — enrich inputs still sparse for one or more sources."
    )
    return out
