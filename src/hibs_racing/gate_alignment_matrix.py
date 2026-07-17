"""Evidence-backed gate alignment matrix for live liquidity routing."""

from __future__ import annotations

import os
from copy import deepcopy
from dataclasses import dataclass
from typing import Any

from hibs_racing.backtest.gate_config_alignment import (
    ALIGNED_OVERLAY_SPECS,
    BLEND_SPECS,
    INDUSTRY_STANDARD_ANCHORS,
    _gate3_paper,
    _gate7_paper,
    _hybrid_gate3_gate7_paper,
)
from hibs_racing.backtest.gate_impact import gate3_config, gate7_config
from hibs_racing.cards.actionability import _gate2_confidence, value_gate_reason
from hibs_racing.config import load_config

DISARMED_TRACE = "DISARMED_BY_FORENSIC_ALIGNMENT"
PASS_TRACE = "FORENSIC_BLEND_PASS"

# Evaluation priority — forensic blends first, then aligned overlays (walk-forward ROI order).
_BLEND_EVAL_ORDER: tuple[str, ...] = (
    "blend_gate8_gate7",
    "blend_gate3_gate7",
)
_ALIGNED_EVAL_ORDER: tuple[str, ...] = (
    "aligned_regime_gate8",
    "aligned_sniper_gate7",
    "aligned_institutional_gate3",
)


def forensic_alignment_enabled() -> bool:
    return os.environ.get("HIBS_FORENSIC_ALIGNMENT_DISABLED", "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    )


def telemetry_actionable(telemetry: dict[str, Any]) -> bool:
    """Require explicit runner telemetry before forensic enforcement."""
    if not telemetry:
        return False
    keys = (
        "place_ev",
        "combo_bayes_place",
        "official_rating",
        "model_place_prob",
        "ew_combined_ev",
    )
    return any(telemetry.get(k) is not None for k in keys)


@dataclass(frozen=True)
class ForensicAlignmentReport:
    verdict: str  # PASS | REJECT
    blend_id: str | None
    aligned_overlay: str | None
    industry_standard: str | None
    allocated_cap: float
    reason: str
    order_trace: str | None = None
    runner_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "verdict": self.verdict,
            "blend_id": self.blend_id,
            "aligned_overlay": self.aligned_overlay,
            "industry_standard": self.industry_standard,
            "allocated_cap": self.allocated_cap,
            "reason": self.reason,
            "order_trace": self.order_trace,
            "runner_id": self.runner_id,
        }


class GateAlignmentMatrix:
    """
    Locks liquidity routing to evidence-backed walk-forward telemetry configurations.

    Encodes 3 industry standards, 3 aligned overlays, and 2 forensic blends.
    """

    INDUSTRY_STANDARDS = INDUSTRY_STANDARD_ANCHORS
    ALIGNED_OVERLAYS = ALIGNED_OVERLAY_SPECS
    FORENSIC_BLENDS = BLEND_SPECS

    def __init__(self, paper_cfg: dict | None = None, full_cfg: dict | None = None) -> None:
        self._full_cfg = full_cfg if full_cfg is not None else load_config()
        self._paper = deepcopy(paper_cfg if paper_cfg is not None else self._full_cfg.get("paper") or {})
        self._stake_unit = float(self._paper.get("default_stake", 1.0))

    def _lane_paper_cfg(self, lane_id: str) -> dict:
        full = self._full_cfg
        paper = self._paper
        if lane_id == "aligned_institutional_gate3":
            return _gate3_paper(paper, full)
        if lane_id == "aligned_sniper_gate7":
            return _gate7_paper(paper, full)
        if lane_id == "aligned_regime_gate8":
            return _gate3_paper(paper, full)
        if lane_id == "blend_gate3_gate7":
            return _hybrid_gate3_gate7_paper(paper, full)
        if lane_id == "blend_gate8_gate7":
            return _gate7_paper(paper, full)
        return gate3_config(paper, full)

    def _runner_passes(self, runner: dict, paper_cfg: dict) -> bool:
        probe = dict(runner)
        probe["value_flag"] = 1
        return value_gate_reason(probe, paper_cfg) is None

    def _cap_from_gate2(self, runner: dict, paper_cfg: dict) -> float:
        g2 = paper_cfg.get("gate2") if isinstance(paper_cfg.get("gate2"), dict) else {}
        race_cap = g2.get("max_value_per_race")
        if race_cap is None:
            race_cap = 1
        return self._stake_unit * float(race_cap)

    def _cap_regime_blend(self, runner: dict, blend_id: str) -> float:
        spec = BLEND_SPECS[blend_id].get("regime_blend") or {}
        cfg = self._lane_paper_cfg(blend_id)
        conf = _gate2_confidence(runner, cfg)
        trigger = float(spec.get("trigger_confidence", 0.70))
        if conf >= trigger:
            cap = int(spec.get("escalated_max_value_per_race", 1))
        else:
            cap = int(spec.get("default_max_value_per_race", 2))
        return self._stake_unit * float(cap)

    def _allocated_cap(self, lane_id: str, runner: dict) -> float:
        if lane_id == "blend_gate8_gate7":
            return self._cap_regime_blend(runner, lane_id)
        if lane_id == "aligned_regime_gate8":
            g8 = self._full_cfg.get("experimental_replay_lanes", {}).get("gate8_regime_blend", {})
            spec = {
                "trigger_confidence": g8.get("trigger_confidence", 0.70),
                "default_max_value_per_race": g8.get("default_max_value_per_race", 2),
                "escalated_max_value_per_race": g8.get("escalated_max_value_per_race", 1),
            }
            cfg = self._lane_paper_cfg(lane_id)
            conf = _gate2_confidence(runner, cfg)
            cap = (
                int(spec["escalated_max_value_per_race"])
                if conf >= float(spec["trigger_confidence"])
                else int(spec["default_max_value_per_race"])
            )
            return self._stake_unit * float(cap)
        paper = self._lane_paper_cfg(lane_id)
        return self._cap_from_gate2(runner, paper)

    def evaluate_runner(self, runner: dict) -> ForensicAlignmentReport:
        """Evaluate one runner telemetry dict against blends then aligned overlays."""
        if not forensic_alignment_enabled():
            stake = float(runner.get("stake") or runner.get("requested_stake") or self._stake_unit)
            return ForensicAlignmentReport(
                verdict="PASS",
                blend_id=None,
                aligned_overlay=None,
                industry_standard=None,
                allocated_cap=stake,
                reason="forensic_alignment_disabled",
                order_trace=PASS_TRACE,
                runner_id=str(runner.get("runner_id") or "") or None,
            )

        runner_id = str(runner.get("runner_id") or "") or None

        for blend_id in _BLEND_EVAL_ORDER:
            paper = self._lane_paper_cfg(blend_id)
            if self._runner_passes(runner, paper):
                aligns = ALIGNED_OVERLAY_SPECS.get("aligned_regime_gate8", {}).get("aligns_to")
                if blend_id == "blend_gate8_gate7":
                    aligns = INDUSTRY_STANDARD_ANCHORS["std_regime_blend_gate8"]["lane_kind"]
                return ForensicAlignmentReport(
                    verdict="PASS",
                    blend_id=blend_id,
                    aligned_overlay=None,
                    industry_standard=BLEND_SPECS[blend_id].get("description"),
                    allocated_cap=self._allocated_cap(blend_id, runner),
                    reason=f"forensic_blend_pass:{blend_id}",
                    order_trace=PASS_TRACE,
                    runner_id=runner_id,
                )

        for overlay_id in _ALIGNED_EVAL_ORDER:
            paper = self._lane_paper_cfg(overlay_id)
            if self._runner_passes(runner, paper):
                spec = ALIGNED_OVERLAY_SPECS[overlay_id]
                return ForensicAlignmentReport(
                    verdict="PASS",
                    blend_id=None,
                    aligned_overlay=overlay_id,
                    industry_standard=spec.get("aligns_to"),
                    allocated_cap=self._allocated_cap(overlay_id, runner),
                    reason=f"aligned_overlay_pass:{overlay_id}",
                    order_trace=PASS_TRACE,
                    runner_id=runner_id,
                )

        return ForensicAlignmentReport(
            verdict="REJECT",
            blend_id=None,
            aligned_overlay=None,
            industry_standard=None,
            allocated_cap=0.0,
            reason="no_blend_or_overlay_pass",
            order_trace=DISARMED_TRACE,
            runner_id=runner_id,
        )

    def evaluate_runner_against_blends(
        self,
        runner_telemetry: list[dict[str, Any]] | dict[str, Any],
    ) -> ForensicAlignmentReport:
        """
        Pipe runner telemetry array through forensic blends and aligned overlays.

        For multi-runner arrays, returns the strictest verdict (any REJECT wins;
        otherwise highest allocated_cap PASS).
        """
        if isinstance(runner_telemetry, dict):
            rows = [runner_telemetry]
        else:
            rows = list(runner_telemetry)

        if not rows:
            return ForensicAlignmentReport(
                verdict="REJECT",
                blend_id=None,
                aligned_overlay=None,
                industry_standard=None,
                allocated_cap=0.0,
                reason="empty_telemetry",
                order_trace=DISARMED_TRACE,
            )

        reports = [self.evaluate_runner(row) for row in rows]
        rejects = [r for r in reports if r.verdict == "REJECT"]
        if rejects:
            return rejects[0]

        best = max(reports, key=lambda r: float(r.allocated_cap or 0.0))
        return best

    def industry_standards_table(self) -> list[dict[str, Any]]:
        """Summary table of encoded industry standards for audit manifests."""
        return [
            {"standard_id": sid, **meta}
            for sid, meta in self.INDUSTRY_STANDARDS.items()
        ]
