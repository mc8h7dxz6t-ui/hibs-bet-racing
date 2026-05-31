from hibs_racing.live.execution_config import (
    betfair_configured,
    betfair_enabled,
    execution_summary,
    preferred_execution_venues,
)


def test_analytics_mode_execution_disabled():
    assert betfair_enabled() is False
    assert preferred_execution_venues() == []
    summary = execution_summary()
    assert summary["disabled"] is True
    assert summary["mode"] == "analytics"
    assert summary["dry_run"] is True
    assert summary["preferred_venues"] == []


def test_betfair_configured_requires_all_creds(monkeypatch):
    monkeypatch.delenv("BETFAIR_APP_KEY", raising=False)
    monkeypatch.delenv("BETFAIR_USERNAME", raising=False)
    monkeypatch.delenv("BETFAIR_PASSWORD", raising=False)
    assert betfair_configured() is False

    monkeypatch.setenv("BETFAIR_APP_KEY", "k")
    monkeypatch.setenv("BETFAIR_USERNAME", "u")
    monkeypatch.setenv("BETFAIR_PASSWORD", "p")
    assert betfair_configured() is True
