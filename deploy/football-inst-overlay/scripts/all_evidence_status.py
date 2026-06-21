#!/usr/bin/env python3
"""Unified evidence + ops status across football, racing, trading."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))


def _load_json(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def gather_status() -> dict:
    out: dict = {"ts": datetime.now(timezone.utc).isoformat()}

    try:
        from hibs_predictor.forward_evidence import forward_evidence_gates

        fb = forward_evidence_gates()
        out["football"] = {
            "buyer_ready": fb.get("buyer_ready"),
            "buyer_readiness_score": fb.get("buyer_readiness_score"),
            "commercial_tier": fb.get("commercial_tier"),
            "evidence_grade": fb.get("evidence_grade"),
            "matchdays_7d": fb.get("matchdays_7d"),
            "gates_pass": sum(1 for g in fb.get("gates", []) if g.get("pass")),
            "gates_total": len(fb.get("gates", [])),
            "next_actions": (fb.get("next_actions") or [])[:5],
        }
    except Exception as exc:
        out["football"] = {"error": str(exc)[:160]}

    try:
        from hibs_predictor.racing_evidence import racing_evidence_gates

        rc = racing_evidence_gates()
        out["racing"] = {
            "buyer_ready": rc.get("buyer_ready"),
            "buyer_readiness_score": rc.get("buyer_readiness_score"),
            "commercial_tier": rc.get("commercial_tier"),
            "evidence_grade": rc.get("evidence_grade"),
            "gates_pass": sum(1 for g in rc.get("gates", []) if g.get("pass")),
            "gates_total": len(rc.get("gates", [])),
            "next_actions": (rc.get("next_actions") or [])[:5],
        }
    except Exception as exc:
        out["racing"] = {"error": str(exc)[:160]}

    try:
        from hibs_predictor.inplay_evidence import inplay_evidence_gates

        ip = inplay_evidence_gates()
        out["inplay"] = {
            "buyer_ready": ip.get("buyer_ready"),
            "buyer_readiness_score": ip.get("buyer_readiness_score"),
            "commercial_tier": ip.get("commercial_tier"),
            "evidence_grade": ip.get("evidence_grade"),
            "gates_pass": sum(1 for g in ip.get("gates", []) if g.get("pass")),
            "gates_total": len(ip.get("gates", [])),
            "next_actions": (ip.get("next_actions") or [])[:5],
        }
    except Exception as exc:
        out["inplay"] = {"error": str(exc)[:160]}

    tr_root = Path(os.environ.get("TRADING_INSTALL_ROOT", "/opt/trading-core"))
    day15_script = REPO_ROOT / "scripts" / "evaluate_trading_day15_gate.py"
    if day15_script.is_file():
        try:
            proc = subprocess.run(
                [sys.executable, str(day15_script), "--trading-root", str(tr_root), "--json"],
                capture_output=True,
                text=True,
                timeout=30,
                cwd=str(REPO_ROOT),
            )
            if proc.stdout.strip():
                out["trading_day15"] = json.loads(proc.stdout)
            else:
                out["trading_day15"] = {"error": (proc.stderr or "no output")[:120]}
        except Exception as exc:
            out["trading_day15"] = {"error": str(exc)[:120]}

    stack = _load_json(Path("/var/log/hibs-bet/three-stack-status.json"))
    if stack:
        out["three_stack"] = stack
    inst = _load_json(Path("/var/log/hibs-bet/institutional-status.json"))
    if inst:
        out["institutional"] = inst

    return out


def main() -> int:
    json_only = "--json" in sys.argv
    report = gather_status()
    if json_only:
        print(json.dumps(report, indent=2, default=str))
        return 0
    print(f"==> All evidence status ({report['ts']})")
    for stack in ("football", "racing", "inplay"):
        row = report.get(stack) or {}
        if row.get("error"):
            print(f"{stack}: ERROR {row['error']}")
        else:
            print(
                f"{stack}: grade={row.get('evidence_grade')} "
                f"score={row.get('buyer_readiness_score')} "
                f"ready={row.get('buyer_ready')} "
                f"gates={row.get('gates_pass')}/{row.get('gates_total')}"
            )
    d15 = report.get("trading_day15") or {}
    if d15:
        print(f"trading_day15: {d15.get('verdict', d15.get('error', '?'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
