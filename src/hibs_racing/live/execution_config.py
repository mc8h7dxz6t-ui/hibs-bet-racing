from __future__ import annotations

import os

from hibs_racing.config import load_config


def betfair_enabled(cfg: dict | None = None) -> bool:
    """Phase C Betfair routing — off by default until access + mapping are ready."""
    cfg = cfg or load_config()
    env = os.environ.get("HIBS_BETFAIR_ENABLED", "").strip().lower()
    if env in {"0", "false", "no", "off"}:
        return False
    if env in {"1", "true", "yes", "on"}:
        return True
    return bool(cfg.get("execution", {}).get("betfair_enabled", False))


def betfair_configured() -> bool:
    return bool(
        os.environ.get("BETFAIR_APP_KEY", "").strip()
        and os.environ.get("BETFAIR_USERNAME", "").strip()
        and os.environ.get("BETFAIR_PASSWORD", "").strip()
    )


def preferred_execution_venues(cfg: dict | None = None) -> list[str]:
    cfg = cfg or load_config()
    venues = [str(v).lower() for v in cfg.get("execution", {}).get("preferred_venues", ["matchbook", "betfair"])]
    if not betfair_enabled(cfg):
        venues = [v for v in venues if v != "betfair"]
    return venues or ["matchbook"]


def execution_summary(cfg: dict | None = None) -> dict:
    cfg = cfg or load_config()
    ex = cfg.get("execution", {})
    live = os.environ.get("HIBS_EXECUTION_LIVE", "").strip().lower() in {"1", "true", "yes"}
    return {
        "dry_run": not live and bool(ex.get("dry_run", True)),
        "betfair_enabled": betfair_enabled(cfg),
        "betfair_configured": betfair_configured(),
        "preferred_venues": preferred_execution_venues(cfg),
        "max_stake": float(ex.get("max_stake", 2.0)),
    }
