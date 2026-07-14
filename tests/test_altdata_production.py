"""Production feed fetcher tests."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from altdata.feeds import fetch_production_context


@pytest.fixture
def frankfurter_json():
    return {
        "amount": 1.0,
        "base": "GBP",
        "date": "2026-06-23",
        "rates": {"USD": 1.27, "EUR": 1.17},
    }


def test_fetch_production_context_maps_fields(frankfurter_json):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.return_value = frankfurter_json
    with patch("altdata.feeds.httpx.get", return_value=mock_resp):
        ctx = fetch_production_context("fx_gbp_cross")
    assert ctx["fare_price"] == 1.27
    assert ctx["route_code"] == "GBP"
    assert ctx["seat_count"] == 1.0
    assert ctx["production_feed_id"] == "fx_gbp_cross"
