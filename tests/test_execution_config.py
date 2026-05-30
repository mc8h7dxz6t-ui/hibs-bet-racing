import os

from hibs_racing.live.execution_config import (
    betfair_configured,
    betfair_enabled,
    execution_summary,
    preferred_execution_venues,
)


def test_betfair_disabled_by_default_config():
    cfg = {"execution": {"betfair_enabled": False, "preferred_venues": ["matchbook", "betfair"]}}
    assert betfair_enabled(cfg) is False
    assert preferred_execution_venues(cfg) == ["matchbook"]


def test_betfair_env_override_enable():
    cfg = {"execution": {"betfair_enabled": False}}
    os.environ["HIBS_BETFAIR_ENABLED"] = "1"
    try:
        assert betfair_enabled(cfg) is True
        assert "betfair" in preferred_execution_venues(cfg)
    finally:
        os.environ.pop("HIBS_BETFAIR_ENABLED", None)


def test_betfair_env_override_disable():
    cfg = {"execution": {"betfair_enabled": True}}
    os.environ["HIBS_BETFAIR_ENABLED"] = "0"
    try:
        assert betfair_enabled(cfg) is False
        assert preferred_execution_venues(cfg) == ["matchbook"]
    finally:
        os.environ.pop("HIBS_BETFAIR_ENABLED", None)


def test_execution_summary_includes_routing_fields():
    cfg = {
        "execution": {
            "dry_run": True,
            "betfair_enabled": False,
            "preferred_venues": ["matchbook"],
            "max_stake": 3.5,
        }
    }
    summary = execution_summary(cfg)
    assert summary["dry_run"] is True
    assert summary["betfair_enabled"] is False
    assert summary["preferred_venues"] == ["matchbook"]
    assert summary["max_stake"] == 3.5


def test_betfair_configured_requires_all_creds(monkeypatch):
    monkeypatch.delenv("BETFAIR_APP_KEY", raising=False)
    monkeypatch.delenv("BETFAIR_USERNAME", raising=False)
    monkeypatch.delenv("BETFAIR_PASSWORD", raising=False)
    assert betfair_configured() is False

    monkeypatch.setenv("BETFAIR_APP_KEY", "k")
    monkeypatch.setenv("BETFAIR_USERNAME", "u")
    monkeypatch.setenv("BETFAIR_PASSWORD", "p")
    assert betfair_configured() is True
