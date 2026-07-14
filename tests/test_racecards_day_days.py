"""Regression: load_racecard_frames(days=N) must not inherit default day=1."""

from __future__ import annotations

import pytest

from hibs_racing.ingest.racecards import fetch_racecards, load_racecard_frames


def test_fetch_racecards_rejects_day_and_days_together() -> None:
    with pytest.raises(ValueError, match="not both"):
        fetch_racecards(day=1, days=2)


def test_load_racecard_frames_days_only_passes_kwargs(monkeypatch) -> None:
    captured: dict = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("hibs_racing.ingest.racecards.fetch_racecards", fake_fetch)
    with pytest.raises(Exception):
        load_racecard_frames(days=2, region="ire")
    assert captured == {"day": None, "days": 2, "region": "ire"}


def test_load_racecard_frames_default_day(monkeypatch) -> None:
    captured: dict = {}

    def fake_fetch(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("hibs_racing.ingest.racecards.fetch_racecards", fake_fetch)
    with pytest.raises(Exception):
        load_racecard_frames(region="gb")
    assert captured == {"day": None, "days": None, "region": "gb"}
