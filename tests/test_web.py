import pytest

pytest.importorskip("flask")


def test_create_app():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    ping = client.get("/api/ping")
    assert ping.status_code == 200
    assert ping.get_json()["product"] == "hibs-racing"
    home = client.get("/")
    assert home.status_code == 200
    assert b"hibs-product-bar" in home.data
    assert b"Football" in home.data
    assert b"Racing" in home.data
    cards = client.get("/cards")
    assert cards.status_code == 200
    tips = client.get("/tips")
    assert tips.status_code == 200
    assert b"Paste today" in tips.data


def test_cards_deep_link_query_params():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/cards?meeting=1-test&race=race-1-test-r1&runner_id=abc")
    assert resp.status_code == 200
    assert b'id="racecard-nav-state"' in resp.data
    assert b'data-initial-meeting="1-test"' in resp.data
    assert b'data-initial-race="race-1-test-r1"' in resp.data
    assert b'data-highlight-runner="abc"' in resp.data


def test_insights_page_loads():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/insights")
    assert resp.status_code == 200
    assert b"Best 10 picks" in resp.data


def test_tracker_page_public():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/tracker?days=60")
    assert resp.status_code == 200
    assert b"Live Paper Track Record" in resp.data
    assert b"Cumulative P" in resp.data
    assert b"Institutional Data Room" in resp.data
    assert b"Download May OOS Track Record" in resp.data
    assert resp.headers.get("Cache-Control", "").startswith("public")

    oos = client.get("/tracker?backtest=1")
    assert oos.status_code == 200
    assert b"OOS holdout" in oos.data

    faq = client.get("/docs/technical-faq")
    assert faq.status_code == 200
    assert b"Technical" in faq.data or b"Due Diligence" in faq.data or b"FAQ" in faq.data

    api = client.get("/api/tracker?days=30")
    assert api.status_code == 200
    payload = api.get_json()
    assert payload.get("public") is True
    assert "pnl_curve" in payload
    assert "clv" in payload


def test_status_page_analytics_batch_mode():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/status")
    assert resp.status_code == 200
    assert b"Batch operations" in resp.data
    assert b"06:00 daily batch" in resp.data
    assert b"Automation Status" in resp.data
    assert b"SHA-256 Ledger Chain Verification" in resp.data
    assert b"Execution routing" not in resp.data

    assert client.get("/api/execution/log").status_code == 404
    assert client.get("/api/execution/preview").status_code == 404

    poll = client.get("/api/market-steam?poll=1")
    assert poll.status_code == 403


def test_status_page_ranker_attribution():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/status")
    assert resp.status_code == 200
    assert b"Ranker live verification" in resp.data
    assert b"lgbm_ranker_features.json" in resp.data

    api = client.get("/api/ranker/attribution")
    assert api.status_code == 200
    payload = api.get_json()
    assert "matrix" in payload
    assert "checks" in payload
