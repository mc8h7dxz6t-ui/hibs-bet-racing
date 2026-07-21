import pytest

pytest.importorskip("flask")


def test_ui_shell_static_v_query_param():
    from hibs_racing.ui_shell import static_v, ui_shell_context

    from hibs_racing.web import create_app

    app = create_app()
    with app.test_request_context("/cards"):
        url = static_v("hibs_theme.css")
        assert "hibs_theme.css" in url
        assert "v=" in url
        ctx = ui_shell_context()
        assert callable(ctx["static_v"])
        assert ctx.get("hibs_theme_lite") is True


def test_ui_asset_version_env_override(monkeypatch):
    from hibs_racing.ui_shell import static_v

    from hibs_racing.web import create_app

    monkeypatch.setenv("HIBS_UI_ASSET_VERSION", "testver")
    app = create_app()
    with app.test_request_context("/cards"):
        url = static_v("hibs_theme.css")
    assert "v=testver" in url


def test_base_template_uses_theme_css_not_legacy_inline_tokens():
    from pathlib import Path

    text = Path("templates/base.html").read_text(encoding="utf-8")
    assert "hibs_theme.css" in text
    assert "--hibs-navy-deep:#0b1220" not in text.replace(" ", "")
    assert 'data-hibs-theme="pastel"' in text


def test_product_switcher_urls_local(monkeypatch):
    from hibs_racing.web import create_app

    monkeypatch.delenv("HIBS_RACING_PUBLIC_URL", raising=False)
    monkeypatch.delenv("HIBS_URL_PREFIX", raising=False)
    monkeypatch.delenv("HIBS_FOOTBALL_HOME_URL", raising=False)
    app = create_app()
    client = app.test_client()
    resp = client.get("/cards")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", errors="replace")
    assert 'href="/cards"' in html
    assert "hibs_theme.css?v=" in html
    assert "hibs_mobile.css?v=" in html
    assert 'content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no"' in html
    assert "racing_ui.js?v=" in html
    assert "hibs_harvested_logo.png?v=" in html
    assert "Trading" in html
    assert "Lines" in html
    assert "https://hibs-bet.co.uk/" in html


def test_product_switcher_urls_public(monkeypatch):
    from hibs_racing.web import create_app

    monkeypatch.setenv("HIBS_RACING_PUBLIC_URL", "https://hibs-bet.co.uk/racing")
    monkeypatch.setenv("HIBS_FOOTBALL_HOME_URL", "https://hibs-bet.co.uk/")
    app = create_app()
    client = app.test_client()
    resp = client.get("/cards")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", errors="replace")
    assert 'href="https://hibs-bet.co.uk/racing/cards"' in html
    assert 'href="https://hibs-bet.co.uk/"' in html


def test_subpath_rewrites_internal_nav(monkeypatch):
    from hibs_racing.web import create_app

    monkeypatch.setenv("HIBS_URL_PREFIX", "/racing")
    monkeypatch.setenv("HIBS_FOOTBALL_HOME_URL", "https://hibs-bet.co.uk/")
    app = create_app()
    resp = app.test_client().get("/cards")
    html = resp.data.decode("utf-8", errors="replace")
    assert 'href="/racing/insights"' in html
    assert 'id="meeting-select"' in html or 'Racecards' in html
    assert 'data-api-url="/api/racing/portfolio/summary"' in html
