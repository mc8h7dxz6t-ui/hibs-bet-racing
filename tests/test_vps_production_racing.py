"""Tests for VPS production racing profile."""

from __future__ import annotations

from pathlib import Path


def test_apply_production_racing_script_exists():
    root = Path(__file__).resolve().parents[1]
    script = root / "deploy" / "apply-vps-production-racing.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "HIBS_OBSERVATION_LANE=0" in text
    assert "HIBS_RACING_PRODUCTION=1" in text
