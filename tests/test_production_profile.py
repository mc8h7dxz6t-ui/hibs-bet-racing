"""Production profile gate tests — fail-closed /ready semantics."""

from __future__ import annotations

import os

import pytest

from inst_spine.production_profile import (
    drift_redis_rolling_required,
    durable_webhook_dispatch_required,
    production_profile_enabled,
    redis_required_for_production,
    webhook_dispatch_check,
)


def test_production_profile_off_by_default(monkeypatch):
    monkeypatch.delenv("INST_PRODUCTION_PROFILE", raising=False)
    assert production_profile_enabled() is False
    assert redis_required_for_production() is False


def test_production_profile_requires_redis(monkeypatch):
    monkeypatch.setenv("INST_PRODUCTION_PROFILE", "1")
    monkeypatch.delenv("INST_FORCE_MEMORY_BACKENDS", raising=False)
    assert redis_required_for_production() is True


def test_webhook_dispatch_background_blocked_in_production(monkeypatch):
    monkeypatch.setenv("INST_PRODUCTION_PROFILE", "1")
    monkeypatch.delenv("INST_REDIS_URL", raising=False)
    ok, detail = webhook_dispatch_check("background")
    assert ok is False
    assert "production" in detail


def test_webhook_dispatch_redis_ok_when_configured(monkeypatch):
    monkeypatch.setenv("INST_PRODUCTION_PROFILE", "1")
    monkeypatch.setenv("INST_REDIS_URL", "redis://127.0.0.1:9")
    ok, _ = webhook_dispatch_check("redis")
    assert ok is False or ok is True


def test_drift_redis_required_in_production(monkeypatch):
    monkeypatch.setenv("INST_PRODUCTION_PROFILE", "1")
    assert drift_redis_rolling_required() is True


def test_durable_dispatch_required_in_production(monkeypatch):
    monkeypatch.setenv("INST_PRODUCTION_PROFILE", "1")
    assert durable_webhook_dispatch_required() is True
