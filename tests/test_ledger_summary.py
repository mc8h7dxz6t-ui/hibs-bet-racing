"""Ledger summary API tests."""

from __future__ import annotations

import pytest

pytest.importorskip("flask")


def test_ledger_summary_endpoint_shape():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/api/portfolio/ledger-summary")
    assert resp.status_code in (200, 503)
    payload = resp.get_json()
    assert "status" in payload
    if payload.get("status") == "ok":
        for key in (
            "settled_rows",
            "total_pnl",
            "value_pick_pnl",
            "ledger_kind",
            "checked_at",
        ):
            assert key in payload
        assert payload["ledger_kind"] == "forward"


def test_ledger_summary_invalid_days():
    from hibs_racing.web import create_app

    app = create_app()
    client = app.test_client()
    resp = client.get("/api/portfolio/ledger-summary?days=abc")
    assert resp.status_code == 400


def test_build_ledger_summary_payload_module():
    from hibs_racing.portfolio.ledger_summary import build_ledger_summary_payload

    payload = build_ledger_summary_payload()
    assert payload["status"] in ("ok", "error")
    if payload["status"] == "ok":
        assert payload["settled_rows"] >= 0
        assert isinstance(payload["total_pnl"], (int, float))
