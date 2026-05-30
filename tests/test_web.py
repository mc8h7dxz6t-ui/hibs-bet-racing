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
    assert b"hibs-racing" in home.data
    tips = client.get("/tips")
    assert tips.status_code == 200
    assert b"Paste today" in tips.data
