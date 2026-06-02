"""Gate2 portfolio-cap sensitivity — caps ON vs OFF on the same scored snapshot window."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from hibs_racing.backtest.gate_benchmark import _delta, run_gate_benchmark
from hibs_racing.config import db_path, load_config


@dataclass
class Gate2CapSensitivityReport:
    start: str
    end: str
    with_caps: dict
    without_caps: dict
    delta_without_vs_with: dict
    caps_material: bool
    message: str

    def to_dict(self) -> dict:
        return {
            "start": self.start,
            "end": self.end,
            "with_caps": self.with_caps,
            "without_caps": self.without_caps,
            "delta_without_vs_with": self.delta_without_vs_with,
            "caps_material": self.caps_material,
            "message": self.message,
        }


def run_gate2_cap_sensitivity(
    *,
    start: str | None = None,
    end: str | None = None,
    database: Path | None = None,
    days: int | None = 90,
    use_snapshots: bool = True,
) -> Gate2CapSensitivityReport:
    cfg = load_config()
    db = database or db_path(cfg)
    if start is None or end is None:
        end_dt = datetime.now(timezone.utc).date()
        if end:
            end_dt = datetime.strptime(end, "%Y-%m-%d").date()
        start_dt = end_dt - timedelta(days=int(days or 90))
        if start:
            start_dt = datetime.strptime(start, "%Y-%m-%d").date()
        start_s = start_dt.isoformat()
        end_s = end_dt.isoformat()
    else:
        start_s, end_s = start, end

    with_caps = run_gate_benchmark(
        start=start_s,
        end=end_s,
        database=db,
        use_snapshots=use_snapshots,
        gate2_caps=True,
        include_slippage=False,
    )
    without_caps = run_gate_benchmark(
        start=start_s,
        end=end_s,
        database=db,
        use_snapshots=use_snapshots,
        gate2_caps=False,
        include_slippage=False,
    )

    delta = _delta(without_caps.gate2, with_caps.gate2)
    roi_delta = delta.get("roi_change_pp")
    caps_material = roi_delta is not None and abs(float(roi_delta)) >= 5.0
    msg = (
        f"Gate2 caps sensitivity {start_s} → {end_s}: "
        f"with_caps picks={with_caps.gate2.get('picks')}, "
        f"without_caps picks={without_caps.gate2.get('picks')}, "
        f"ROI delta (no caps - caps)={roi_delta}pp."
    )
    return Gate2CapSensitivityReport(
        start=start_s,
        end=end_s,
        with_caps={
            "none": with_caps.none,
            "gate1": with_caps.gate1,
            "gate2": with_caps.gate2,
            "blocked_reasons_gate2": with_caps.blocked_reasons_gate2,
            "snapshot_source": with_caps.snapshot_source,
        },
        without_caps={
            "none": without_caps.none,
            "gate1": without_caps.gate1,
            "gate2": without_caps.gate2,
            "blocked_reasons_gate2": without_caps.blocked_reasons_gate2,
            "snapshot_source": without_caps.snapshot_source,
        },
        delta_without_vs_with=delta,
        caps_material=caps_material,
        message=msg,
    )
