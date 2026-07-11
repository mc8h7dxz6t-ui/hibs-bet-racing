"""Regression: web.py gains fmt_* filters when missing (VPS hotfix path)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def _load_web_format():
    root = Path(__file__).resolve().parents[1] / "src"
    spec = importlib.util.spec_from_file_location(
        "hibs_predictor.web_format",
        root / "hibs_predictor" / "web_format.py",
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["hibs_predictor.web_format"] = mod
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


def test_web_format_exports_fmt_roi():
    mod = _load_web_format()
    assert mod.fmt_roi(12.34) == "+12.3%"
    assert mod.fmt_num(None) == "—"
    assert mod.fmt_pct(0.42) == "42%"


def test_dashboard_fix_lib_exists():
    lib = Path(__file__).resolve().parents[1] / "scripts" / "lib_football_dashboard_fix.sh"
    script = Path(__file__).resolve().parents[1] / "scripts" / "vps_football_fix_dashboard_500.sh"
    assert lib.is_file(), "lib_football_dashboard_fix.sh missing"
    assert script.is_file(), "vps_football_fix_dashboard_500.sh missing"
    text = lib.read_text(encoding="utf-8")
    assert "football_vps_install_web_format" in text
    assert "football_vps_patch_web_filters" in text
    assert "fmt_roi" in text
