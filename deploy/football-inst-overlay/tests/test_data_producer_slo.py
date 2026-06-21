"""Tests for inst++ data producer SLO."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest


def test_gather_health_light_minimal():
    from hibs_predictor.health_probe import gather_health_light

    out = gather_health_light()
    assert out.get("mode") == "light"
    assert "audit_ops" in out
    assert out.get("apis") == []


def test_augment_health_light_includes_data_producer():
    from hibs_predictor.health_quality_narrative import augment_health_light
    from hibs_predictor.health_probe import gather_health_light

    out = augment_health_light(gather_health_light())
    assert out.get("mode") == "light"
    assert "data_producer" in out


def test_football_fixture_bundle_cache_miss():
    from hibs_predictor.data_producer_slo import football_fixture_bundle_status

    with patch("hibs_predictor.cache.Cache.peek", return_value=None):
        st = football_fixture_bundle_status()
    assert st["ok"] is False
    assert st["cache_hit"] is False


def test_build_data_producer_snapshot_shape():
    from hibs_predictor.data_producer_slo import build_data_producer_snapshot

    with patch(
        "hibs_predictor.data_producer_slo.football_fixture_bundle_status",
        return_value={"ok": True, "fixture_count": 3},
    ), patch(
        "hibs_predictor.data_producer_slo.fve_lines_export_status",
        return_value={"ok": True, "fixture_count": 3},
    ), patch(
        "hibs_predictor.data_producer_slo.fve_remote_status",
        return_value={"ok": True, "reachable": True, "paused": False},
    ), patch(
        "hibs_predictor.data_producer_slo.racing_card_freshness_status",
        return_value={"ok": True, "card_fresh": True},
    ), patch(
        "hibs_predictor.data_producer_slo.football_health_light_status",
        return_value={"ok": True, "latency_ms": 50},
    ):
        snap = build_data_producer_snapshot()
    assert snap["layer"] == "data_producer_slo"
    assert snap["ok"] is True
    assert "producers" in snap
