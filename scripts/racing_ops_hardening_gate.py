#!/usr/bin/env python3
"""Racing ops hardening gate — all checks must pass (100%) before raceform cron install.

  PYTHONPATH=src python3 scripts/racing_ops_hardening_gate.py
  PYTHONPATH=src python3 scripts/racing_ops_hardening_gate.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Tuple

ROOT = Path(__file__).resolve().parents[1]


def _check_sportinglife_parser() -> Tuple[bool, str]:
    from hibs_racing.scrapers.sportinglife_client import _parse_fractional_sp, parse_results_from_html

    assert _parse_fractional_sp("5/1") == 6.0
    html = '<article data-course="Ascot"><span class="horse-name">Fast Horse</span><span class="price">7/2</span></article>'
    rows = parse_results_from_html(html, card_date="2026-08-02")
    if not rows or rows[0].get("horse_name") != "Fast Horse":
        return False, "sportinglife parse failed"
    return True, "sportinglife parser ok"


def _check_raceform_sync_script() -> Tuple[bool, str]:
    script = ROOT / "scripts/sync_raceform_baseline.sh"
    if not script.is_file():
        return False, "sync_raceform_baseline.sh missing"
    text = script.read_text(encoding="utf-8")
    if "ingest-raceform" not in text:
        return False, "ingest-raceform not wired"
    return True, "raceform sync script ok"


def _check_cron_wiring() -> Tuple[bool, str]:
    cron = ROOT / "deploy/cron-hibs-raceform-sync.sh"
    script = ROOT / "scripts/sync_raceform_baseline.sh"
    for path in (cron, script):
        if not path.is_file():
            return False, f"missing {path.name}"
    text = cron.read_text(encoding="utf-8")
    if "sync_raceform_baseline.sh" not in text:
        return False, "cron not wired to sync script"
    if "sportinglife_client" not in text:
        return False, "sportinglife probe missing from cron"
    return True, "cron wiring ok"


def _check_engine_runner_store() -> Tuple[bool, str]:
    path = ROOT / "src/hibs_racing/features/engine_runner_store.py"
    if not path.is_file():
        return False, "engine_runner_store missing"
    text = path.read_text(encoding="utf-8")
    if "engine_runner_features" not in text:
        return False, "engine_runner_features table missing"
    return True, "engine runner store ok"


def _run_pytest_ops_suite() -> Tuple[bool, str]:
    tests = [
        "tests/test_sportinglife_client.py",
        "tests/test_racing_ops_hardening_gate.py",
    ]
    existing = [str(ROOT / t) for t in tests if (ROOT / t).is_file()]
    if not existing:
        return False, "no test files found"
    env = {**os.environ, "PYTHONPATH": str(ROOT / "src")}
    if not env.get("HOME"):
        env["HOME"] = str(Path.home() or "/tmp")
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            *existing,
            "-q",
            "--tb=no",
            "-k",
            "not test_racing_hardening_gate_module_runs",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
    )
    tail = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        return False, tail.strip()[-400:] or f"pytest exit {proc.returncode}"
    return True, tail.strip().split("\n")[-1] if tail.strip() else "pytest ok"


CHECKS: List[Tuple[str, Callable[[], Tuple[bool, str]]]] = [
    ("sportinglife_parser", _check_sportinglife_parser),
    ("raceform_sync_script", _check_raceform_sync_script),
    ("cron_wiring", _check_cron_wiring),
    ("engine_runner_store", _check_engine_runner_store),
    ("pytest_ops_suite", _run_pytest_ops_suite),
]


def run_gate() -> Dict[str, Any]:
    results: List[Dict[str, Any]] = []
    for name, fn in CHECKS:
        try:
            ok, detail = fn()
        except Exception as exc:
            ok, detail = False, str(exc)[:200]
        results.append({"check": name, "ok": bool(ok), "detail": detail})
    passed = sum(1 for r in results if r["ok"])
    total = len(results)
    rate = round(100.0 * passed / total, 1) if total else 0.0
    return {
        "schema": "racing_ops_hardening_gate_v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "ok": passed == total and total > 0,
        "pass_rate_pct": rate,
        "passed": passed,
        "total": total,
        "checks": results,
        "hardening_allowed": passed == total and total > 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Racing ops hardening gate (100% required)")
    parser.add_argument("--json", action="store_true", help="JSON only")
    args = parser.parse_args()
    report = run_gate()
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(f"Racing ops hardening gate: {report['passed']}/{report['total']} ({report['pass_rate_pct']}%)")
        for row in report["checks"]:
            mark = "OK " if row["ok"] else "RED"
            print(f"  {mark} {row['check']}: {row['detail'][:120]}")
        if report["ok"]:
            print("HARDENING ALLOWED — 100% pass")
        else:
            print("HARDENING BLOCKED — fix failures and re-run gate")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
