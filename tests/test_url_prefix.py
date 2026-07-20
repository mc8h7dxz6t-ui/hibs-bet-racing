"""Production /racing subpath HTML rewriting."""

from __future__ import annotations

from flask import Flask

from hibs_racing.url_prefix import apply_url_prefix, prefix_path, racing_api_path, rewrite_html_paths


def test_prefix_path_api_and_nav():
    assert prefix_path("/cards", "/racing") == "/racing/cards"
    assert prefix_path("/api/monitor", "/racing") == "/api/racing/monitor"
    assert prefix_path("/racing/cards", "/racing") == "/racing/cards"
    assert prefix_path("https://example.com/x", "/racing") == "https://example.com/x"


def test_rewrite_html_paths():
    html = '<a href="/insights">x</a><script>fetch("/api/monitor")</script>'
    out = rewrite_html_paths(html, "/racing")
    assert 'href="/racing/insights"' in out
    assert 'fetch("/api/racing/monitor")' in out


def test_rewrite_data_fetch_url():
    html = '<div data-fetch-url="/api/tips/combinations" data-tips-url="/tips"></div>'
    out = rewrite_html_paths(html, "/racing")
    assert 'data-fetch-url="/api/racing/tips/combinations"' in out
    assert 'data-tips-url="/racing/tips"' in out


def test_racing_api_path_production(monkeypatch):
    monkeypatch.setenv("HIBS_URL_PREFIX", "/racing")
    assert racing_api_path("tips/combinations") == "/api/racing/tips/combinations"


def test_racing_api_path_local(monkeypatch):
    monkeypatch.delenv("HIBS_URL_PREFIX", raising=False)
    assert racing_api_path("tips/combinations") == "/api/tips/combinations"


def test_apply_url_prefix_rewrites_cards_page(monkeypatch):
    monkeypatch.setenv("HIBS_URL_PREFIX", "/racing")
    monkeypatch.setenv("HIBS_FOOTBALL_HOME_URL", "https://hibs-bet.co.uk/")
    app = Flask(__name__)

    @app.get("/cards")
    def cards():
        return """<!DOCTYPE html><html><body>
        <a href="/insights">Insights</a>
        <a href="/cards">Cards</a>
        <script>fetch('/api/monitor')</script>
        <div data-api-url="/api/portfolio/summary"></div>
        </body></html>"""

    apply_url_prefix(app)
    html = app.test_client().get("/cards").get_data(as_text=True)
    assert 'href="/racing/insights"' in html
    assert 'href="/racing/cards"' in html
    assert 'fetch(\'/api/racing/monitor\')' in html or 'fetch("/api/racing/monitor")' in html
    assert 'data-api-url="/api/racing/portfolio/summary"' in html


def test_apply_url_prefix_idempotent(monkeypatch):
    monkeypatch.setenv("HIBS_URL_PREFIX", "/racing")
    app = Flask(__name__)
    apply_url_prefix(app)
    apply_url_prefix(app)
    assert getattr(app, "_hibs_url_prefix_applied") is True
