"""Tests for headless fixture warm script."""

from __future__ import annotations


def test_warm_skips_when_fresh_bundle(monkeypatch, capsys):
    import scripts.warm_football_fixtures as warm

    peek = {
        "all": [{"id": 1, "home_team": "A", "away_team": "B"}],
        "by_region": {},
        "by_league": {},
        "dashboard_days": [],
        "value_bets": [],
        "total": 1,
        "fixture_coverage": {},
    }

    monkeypatch.setenv("HIBS_FIXTURE_WARM_FORCE", "0")
    monkeypatch.setenv("HIBS_FIXTURE_WARM_FORCE_REFRESH", "0")
    monkeypatch.setattr(
        "hibs_predictor.web._is_complete_fixture_bundle",
        lambda c: isinstance(c, dict) and bool(c.get("all")),
    )
    monkeypatch.setattr("hibs_predictor.web._all_fixtures_bundle_fresh", lambda b: True)
    monkeypatch.setattr("hibs_predictor.cache.Cache.peek", lambda self, key: peek)

    rc = warm.main()
    out = capsys.readouterr().out.strip()
    assert rc == 0
    assert '"skipped": true' in out
