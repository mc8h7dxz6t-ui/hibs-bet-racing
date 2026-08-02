"""Tests for racing_ops_hardening_gate — must stay at 100%."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_racing_hardening_gate_module_runs():
    proc = subprocess.run(
        ["python3", str(ROOT / "scripts/racing_ops_hardening_gate.py"), "--json"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT / "src")},
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["schema"] == "racing_ops_hardening_gate_v1"
    assert report["hardening_allowed"] is True


def test_racing_hardening_gate_script_exists():
    script = ROOT / "scripts/vps_racing_ops_hardening_gate.sh"
    assert script.is_file()
    assert "racing_ops_hardening_gate.py" in script.read_text(encoding="utf-8")


def test_raceform_cron_gates_before_install():
    text = (ROOT / "deploy/cron-hibs-raceform-sync.sh").read_text(encoding="utf-8")
    assert "vps_racing_ops_hardening_gate" in text or "racing_ops_hardening_gate" in text
