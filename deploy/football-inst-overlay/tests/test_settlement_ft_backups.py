"""Backup FT settlement scrapers (ESPN, FotMob ±1, optional SofaScore)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List

import pytest


def test_espn_event_to_recent_format_finished():
    from hibs_predictor.scrapers.settlement_ft_backups import espn_event_to_recent_format

    event = {
        "id": "760432",
        "date": "2026-06-16T19:00Z",
        "status": {
            "type": {
                "name": "STATUS_FULL_TIME",
                "state": "post",
                "completed": True,
            }
        },
        "competitions": [
            {
                "competitors": [
                    {
                        "homeAway": "home",
                        "score": "3",
                        "team": {"id": 1, "displayName": "France"},
                    },
                    {
                        "homeAway": "away",
                        "score": "1",
                        "team": {"id": 2, "displayName": "Senegal"},
                    },
                ]
            }
        ],
    }
    norm = espn_event_to_recent_format(event)
    assert norm is not None
    assert norm["goals"] == {"home": 3, "away": 1}
    assert norm["teams"]["home"]["name"] == "France"


def test_resolve_ft_from_espn_world_cup(monkeypatch):
    from hibs_predictor import audit_settlement_resolvers as asr

    monkeypatch.setenv("HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK", "1")
    monkeypatch.setenv("HIBS_SETTLE_BACKUP_ESPN", "1")
    kick = "2026-06-16T19:00:00+00:00"
    row = {
        "league_code": "WORLD_CUP",
        "kickoff_iso": kick,
        "home_name": "France",
        "away_name": "Senegal",
    }
    event = {
        "id": "760432",
        "date": "2026-06-16T19:00Z",
        "status": {"type": {"name": "STATUS_FULL_TIME", "completed": True, "state": "post"}},
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "score": "3", "team": {"displayName": "France"}},
                    {"homeAway": "away", "score": "1", "team": {"displayName": "Senegal"}},
                ]
            }
        ],
    }

    def fake_fetch(slug, day, *, cache):
        return [event]

    monkeypatch.setattr(
        "hibs_predictor.scrapers.settlement_ft_backups.fetch_espn_scoreboard",
        fake_fetch,
    )
    monkeypatch.setattr(
        "hibs_predictor.scrapers.fotmob_client.fetch_matches_for_date",
        lambda _day, cache=None: {"leagues": []},
    )

    fid, raw, note, source = asr.resolve_ft_from_scrape_fallback(row, {})
    assert source == "espn_scoreboard"
    assert note == "resolved_espn"
    assert raw["goals"] == {"home": 3, "away": 1}


def test_resolve_ft_psg_alias_via_espn(monkeypatch):
    from hibs_predictor import audit_settlement_resolvers as asr

    monkeypatch.setenv("HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK", "1")
    monkeypatch.setenv("HIBS_SETTLE_BACKUP_ESPN", "1")
    row = {
        "league_code": "UCL",
        "kickoff_iso": "2026-05-30T16:00:00+00:00",
        "home_name": "PSG",
        "away_name": "Arsenal",
    }
    event = {
        "id": "401862897",
        "date": "2026-05-30T16:00Z",
        "status": {"type": {"name": "STATUS_FINAL_PEN", "completed": True, "state": "post"}},
        "competitions": [
            {
                "competitors": [
                    {"homeAway": "home", "score": "1", "team": {"displayName": "Paris Saint-Germain"}},
                    {"homeAway": "away", "score": "1", "team": {"displayName": "Arsenal"}},
                ]
            }
        ],
    }

    def fake_fetch(slug, day, *, cache):
        assert slug == "uefa.champions"
        return [event]

    monkeypatch.setattr(
        "hibs_predictor.scrapers.settlement_ft_backups.fetch_espn_scoreboard",
        fake_fetch,
    )
    monkeypatch.setattr(
        "hibs_predictor.scrapers.fotmob_client.fetch_matches_for_date",
        lambda _day, cache=None: {"leagues": []},
    )

    fid, raw, note, source = asr.resolve_ft_from_scrape_fallback(row, {})
    assert source == "espn_scoreboard"
    assert raw["goals"] == {"home": 1, "away": 1}


def test_fotmob_adjacent_day_fallback(monkeypatch):
    from hibs_predictor.scrapers import settlement_ft_backups as sfb

    monkeypatch.setenv("HIBS_SETTLE_BACKUP_ESPN", "0")
    row = {
        "league_code": "WORLD_CUP",
        "kickoff_iso": "2026-06-17T01:00:00+00:00",
        "home_name": "Brazil",
        "away_name": "Argentina",
    }
    fotmob_match = {
        "id": 991001,
        "utcTime": "2026-06-16T23:30:00.000Z",
        "home": {"longName": "Brazil", "score": 2},
        "away": {"longName": "Argentina", "score": 1},
        "status": {"finished": True, "scoreStr": "2 - 1"},
    }

    def fake_fotmob_day(day, *, cache):
        if day == "2026-06-16":
            return [fotmob_match]
        return []

    monkeypatch.setattr(
        "hibs_predictor.audit_settlement_resolvers._fotmob_matches_for_day",
        fake_fotmob_day,
    )

    fid, raw, note, source = sfb.resolve_ft_from_fotmob_adjacent_days(row, scrape_cache={})
    assert fid == 991001
    assert source == "fotmob_calendar_adjacent"
    assert raw["goals"] == {"home": 2, "away": 1}
