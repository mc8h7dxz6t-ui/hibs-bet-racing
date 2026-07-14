"""Login template shipped with overlay (missing file caused VPS /login 500)."""

from __future__ import annotations

from pathlib import Path


def test_login_template_exists_and_has_form():
    tpl = Path(__file__).resolve().parents[1] / "templates" / "login.html"
    assert tpl.is_file(), "deploy/football-inst-overlay/templates/login.html required for auth"
    text = tpl.read_text(encoding="utf-8")
    assert 'name="password"' in text
    assert "Sign in" in text
    assert "Incorrect password" not in text or "{{ error }}" in text
