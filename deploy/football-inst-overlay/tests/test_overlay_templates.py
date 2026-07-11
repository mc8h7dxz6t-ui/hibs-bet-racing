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


def test_fixture_row_renders_without_btts_keys():
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    tpl_dir = Path(__file__).resolve().parents[1] / "templates"
    row = tpl_dir / "_fixture_row_compact.html"
    text = row.read_text(encoding="utf-8")
    assert "pred.get('btts_prob')" in text
    assert "pred.btts_prob" not in text.replace("pred.get('btts_prob')", "")

    env = Environment(loader=FileSystemLoader(str(tpl_dir)), autoescape=select_autoescape(["html"]))
    tpl = env.from_string("{% for fixture in fixtures %}{% include '_fixture_row_compact.html' %}{% endfor %}")
    html = tpl.render(
        fixtures=[
            {
                "id": 1,
                "home": "A",
                "away": "B",
                "prediction": {"home_win_prob": 0.4},
                "best_odds_1x2": {"home": 2.1},
            }
        ]
    )
    assert "A" in html and "B" in html
