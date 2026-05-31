import json

import pytest

pytest.importorskip("flask")


def test_ui_monetization_save_and_overlay(tmp_path, monkeypatch):
    from hibs_racing.utils import ui_settings as mod

    path = tmp_path / "ui_monetization.json"
    monkeypatch.setattr(mod, "SETTINGS_PATH", path)
    saved = mod.save_ui_monetization(
        {
            "HIBS_AFFILIATE_UTM_SOURCE": "partner_brand",
            "HIBS_AFFILIATE_TRACKING_ID": "track123",
        }
    )
    assert saved["HIBS_AFFILIATE_UTM_SOURCE"] == "partner_brand"
    assert path.exists()
    monkeypatch.delenv("HIBS_AFFILIATE_UTM_SOURCE", raising=False)
    mod.apply_saved_ui_env()
    import os

    assert os.environ.get("HIBS_AFFILIATE_UTM_SOURCE") == "partner_brand"


def test_generate_monetized_link_uses_ui_utm(monkeypatch):
    from hibs_racing.utils.monetization import generate_monetized_link

    monkeypatch.setenv("HIBS_AFFILIATE_UTM_SOURCE", "white_label_co")
    monkeypatch.setenv("HIBS_AFFILIATE_TRACKING_ID", "aff99")
    url = generate_monetized_link("Star", "Ascot", "14:30")
    assert "utm_source=white_label_co" in url
    assert "affiliate_id=aff99" in url


def test_admin_branding_page_loads():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/admin/branding")
    assert resp.status_code == 200
    assert b"Whitelabel Theme Customizer" in resp.data


def test_settings_monetization_page_and_api(tmp_path, monkeypatch):
    from hibs_racing.utils import ui_settings as mod
    from hibs_racing.web import create_app

    path = tmp_path / "ui_monetization.json"
    monkeypatch.setattr(mod, "SETTINGS_PATH", path)

    app = create_app()
    client = app.test_client()
    page = client.get("/settings/monetization")
    assert page.status_code == 200
    assert b"Monetization" in page.data

    post = client.post(
        "/api/settings/monetization",
        data=json.dumps({"HIBS_AFFILIATE_VENUE": "betfair", "HIBS_AFFILIATE_UTM_SOURCE": "saas_demo"}),
        content_type="application/json",
    )
    assert post.status_code == 200
    assert post.get_json()["ok"] is True
    assert path.exists()


def test_tracker_audit_filters_present():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/tracker?backtest=1&days=90")
    assert resp.status_code == 200
    assert b"id=\"filter-course\"" in resp.data or b"trackerAuditFilters" in resp.data
