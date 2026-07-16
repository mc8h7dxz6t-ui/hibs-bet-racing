"""FVE lines proxy and status tests."""

from __future__ import annotations


def test_build_lines_payload_from_bundle():
    from hibs_predictor.fve_lines_proxy import build_lines_payload

    bundle = {
        "all": [
            {
                "home_team": "Arsenal",
                "away_team": "Chelsea",
                "best_odds_1x2": {"home": 2.1, "draw": 3.4, "away": 3.2},
                "league_code": "EPL",
            }
        ]
    }
    payload = build_lines_payload(lambda: bundle, "Arsenal v Chelsea")
    assert payload["ok"] is True
    assert payload["fixture_key"] == "Arsenal v Chelsea"
    assert payload["best_odds_1x2"]["home"] == 2.1


def test_list_fixtures_peek_empty(monkeypatch):
    from hibs_predictor.fve_lines_proxy import list_fixtures_peek

    class _Cache:
        def peek(self, _key):
            return None

    monkeypatch.setattr("hibs_predictor.cache.Cache", lambda: _Cache())
    out = list_fixtures_peek()
    assert out["ok"] is True
    assert out["count"] == 0
    assert out["source"] == "cache_miss"


def test_fve_status_worker_live(monkeypatch):
    from hibs_predictor import fve_status as fs

    fs._CACHE["payload"] = None
    monkeypatch.delenv("HIBS_FVE_FORCE_PAUSED", raising=False)

    def fake_http(url, *, timeout=4.0):
        return True, {
            "status": "ok",
            "paused": False,
            "line_bus": "redis",
            "worker": {"alive": True, "stale": False},
        }, None

    monkeypatch.setattr(fs, "_http_json", fake_http)
    payload = fs.fetch_fve_status(force=True)
    assert payload["reachable"] is True
    assert payload["worker_live"] is True
    assert payload["paused"] is False


def test_fve_status_bridges_backtest_slice(monkeypatch):
    from hibs_predictor import fve_status as fs

    fs._CACHE["payload"] = None

    def fake_http(url, *, timeout=4.0):
        return True, {
            "status": "ok",
            "paused": False,
            "worker": {"alive": True},
            "backtest_slice": {"available": True, "n": 42, "brier_score": 0.61},
            "audit_ops": {"feed_mode": "scrape"},
        }, None

    monkeypatch.setattr(fs, "_http_json", fake_http)
    payload = fs.fetch_fve_status(force=True)
    assert payload["backtest_slice"]["n"] == 42
    assert payload["audit_ops"]["feed_mode"] == "scrape"


def test_fve_status_cached(monkeypatch):
    from hibs_predictor import fve_status as fs

    fs._CACHE["payload"] = None
    calls = {"n": 0}

    def fake_http(url, *, timeout=4.0):
        calls["n"] += 1
        return True, {"status": "ok", "paused": True, "worker": {"alive": False}}, None

    monkeypatch.setattr(fs, "_http_json", fake_http)
    a = fs.fetch_fve_status()
    b = fs.fetch_fve_status()
    assert a["paused"] is True
    assert a["worker_live"] is False
    assert calls["n"] == 1


def test_fve_fixtures_api_route():
    pytest = __import__("pytest")
    pytest.importorskip("flask")
    from hibs_predictor.web import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "test"
    resp = client.get("/api/fve/fixtures")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["ok"] is True
    assert "fixtures" in data


def test_fve_lines_api_not_found():
    pytest = __import__("pytest")
    pytest.importorskip("flask")
    from hibs_predictor.web import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "test"
    resp = client.get("/api/fve/lines/No%20Such%20Fixture")
    assert resp.status_code == 404
    assert resp.get_json()["error"] == "fixture_not_found"


def test_line_trader_page_loads():
    pytest = __import__("pytest")
    pytest.importorskip("flask")
    from hibs_predictor.web import app

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user"] = "test"
    resp = client.get("/line-trader")
    assert resp.status_code == 200
    assert b"Line Shop" in resp.data
    assert b"fve_ws_lines.js" in resp.data
    assert b"line_trader_shop.js" in resp.data
    assert b"hibs-product-bar" in resp.data
    assert b"fixture-select" in resp.data
    assert b"btn-rest" in resp.data
    assert b"lt-shop-mount" in resp.data
    assert b"hibs-deferred-loading" in resp.data
    assert b"Zero-margin true line" in resp.data
    assert b"no order routing" in resp.data


def test_fve_line_shop_config_defaults(monkeypatch):
    from hibs_predictor.fve_status import fve_line_shop_config

    monkeypatch.delenv("HIBS_FVE_DECAY_TIMEOUT_SECS", raising=False)
    monkeypatch.delenv("HIBS_FVE_ARB_DELTA_BPS", raising=False)
    cfg = fve_line_shop_config()
    assert cfg["decay_timeout_secs"] == 120
    assert cfg["arb_delta_bps"] == 50
