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


def test_product_switcher_urls_local(monkeypatch):
    from hibs_racing.web import create_app

    monkeypatch.delenv("HIBS_RACING_PUBLIC_URL", raising=False)
    monkeypatch.delenv("HIBS_FOOTBALL_HOME_URL", raising=False)
    app = create_app()
    client = app.test_client()
    resp = client.get("/cards")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", errors="replace")
    assert 'href="/cards"' in html
    assert "hibs_theme.css?v=" in html
    assert "Trading" in html
    assert "Lines" in html


def test_product_switcher_urls_public(monkeypatch):
    from hibs_racing.web import create_app

    monkeypatch.setenv("HIBS_RACING_PUBLIC_URL", "https://hibs-bet.co.uk/racing")
    monkeypatch.setenv("HIBS_FOOTBALL_HOME_URL", "https://hibs-bet.co.uk")
    app = create_app()
    client = app.test_client()
    resp = client.get("/cards")
    assert resp.status_code == 200
    html = resp.data.decode("utf-8", errors="replace")
    assert 'href="https://hibs-bet.co.uk/racing/cards"' in html
    assert 'href="https://hibs-bet.co.uk/"' in html
