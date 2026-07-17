from __future__ import annotations

import os

from hibs_racing.config import load_config

# Analytics-only product: live exchange routing permanently disabled for compliance / sale.
EXECUTION_DISABLED = True
EXECUTION_DISABLED_MSG = "Analytics mode only — live exchange routing removed."


def execution_disabled() -> bool:
    return EXECUTION_DISABLED


def betfair_enabled(cfg: dict | None = None) -> bool:
    """True when Betfair monetization is armed (credentials + enable flag)."""
    from hibs_racing.utils.monetization import betfair_monetization_armed

    return betfair_monetization_armed()


def betfair_configured() -> bool:
    return bool(
        os.environ.get("BETFAIR_APP_KEY", "").strip()
        and os.environ.get("BETFAIR_USERNAME", "").strip()
        and os.environ.get("BETFAIR_PASSWORD", "").strip()
    )


def preferred_execution_venues(cfg: dict | None = None) -> list[str]:
    from hibs_racing.utils.monetization import active_venues

    if execution_disabled():
        return []
    return active_venues()


def execution_summary(cfg: dict | None = None) -> dict:
    return {
        "disabled": execution_disabled(),
        "mode": "analytics",
        "message": EXECUTION_DISABLED_MSG if execution_disabled() else "",
        "dry_run": True,
        "betfair_enabled": betfair_enabled(),
        "betfair_configured": betfair_configured(),
        "preferred_venues": preferred_execution_venues(cfg),
        "max_stake": 0.0,
        "sub_100ms_exchange": False,
        "co_location": False,
        "institutional_note": (
            "Sub-100ms exchange execution not in analytics license (EXECUTION_DISABLED)."
        ),
    }
