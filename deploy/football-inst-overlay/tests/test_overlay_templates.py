"""Overlay ships all dashboard partial templates (missing files caused VPS / 500)."""

from __future__ import annotations

from pathlib import Path

REQUIRED = (
    "_hibs_brand.html",
    "_launch_wait_overlay.html",
    "_portfolio_bar.html",
    "_product_switcher.html",
    "_term_hint.html",
    "_site_ops_chips.html",
    "_inst_grade_chip.html",
    "_players_dock.html",
    "_betslip_drawer.html",
    "_fixture_row_compact.html",
    "_dashboard_logged_results.html",
    "_dashboard_recent_results.html",
    "_betting_guide.html",
    "_assistant_widget.html",
    "login.html",
)


def test_overlay_dashboard_partials_exist():
    tpl = Path(__file__).resolve().parents[1] / "templates"
    missing = [name for name in REQUIRED if not (tpl / name).is_file()]
    assert not missing, f"missing templates: {missing}"
