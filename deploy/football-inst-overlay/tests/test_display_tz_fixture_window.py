"""Regression: fixture window helpers accept legacy positional/kw callers."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest


def test_fixture_window_start_utc_legacy_positional_now(monkeypatch):
    monkeypatch.setenv("HIBS_DISPLAY_TZ", "UTC")
    from hibs_predictor.display_tz import fixture_window_start_utc, local_today

    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    start = fixture_window_start_utc(now)
    assert start.date() == local_today()
    assert start.hour == 0 and start.minute == 0


def test_fixture_window_end_utc_legacy_positional_window_days(monkeypatch):
    monkeypatch.setenv("HIBS_DISPLAY_TZ", "UTC")
    from hibs_predictor.display_tz import fixture_window_end_utc, fixture_window_start_utc

    now = datetime(2026, 7, 10, 12, 0, tzinfo=timezone.utc)
    start = fixture_window_start_utc()
    end = fixture_window_end_utc(now, 5)
    assert end >= start
    assert (end - start).days >= 4


def test_fixture_window_end_utc_legacy_days_kwarg(monkeypatch):
    monkeypatch.setenv("HIBS_DISPLAY_TZ", "UTC")
    from hibs_predictor.display_tz import fixture_window_end_utc, fixture_window_start_utc

    start = fixture_window_start_utc()
    end = fixture_window_end_utc(days=5)
    assert end >= start


def test_fixture_window_end_utc_days_ahead_kwarg(monkeypatch):
    monkeypatch.setenv("HIBS_DISPLAY_TZ", "UTC")
    from hibs_predictor.display_tz import fixture_window_end_utc

    end = fixture_window_end_utc(days_ahead=2)
    assert end.hour == 23


def test_day_heading_for_local_date_legacy_count(monkeypatch):
    monkeypatch.setenv("HIBS_DISPLAY_TZ", "UTC")
    from datetime import date

    from hibs_predictor.display_tz import day_heading_for_local_date

    today = date(2026, 7, 10)
    assert day_heading_for_local_date("2026-07-10", 5, today) == "Today · 5 fixtures"
    assert day_heading_for_local_date("2026-07-11", 1, today) == "Tomorrow · 1 fixture"
    assert "results" in day_heading_for_local_date("2026-07-09", 3, today).replace(
        "fixtures", "results"
    )
