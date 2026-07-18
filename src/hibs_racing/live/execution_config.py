from __future__ import annotations

import os

from hibs_racing.config import load_config

EXECUTION_DISABLED_MSG = (
    "Analytics mode — live exchange routing requires "
    "HIBS_RACING_LIVE_ROUTING_ALLOWED=1 and HIBS_RACING_CONFIRM_LIVE=YES."
)


def _env_truthy(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in ("1", "true", "yes", "on")


def live_routing_allowed() -> bool:
    """Primary arm — must be explicitly enabled."""
    return _env_truthy("HIBS_RACING_LIVE_ROUTING_ALLOWED")


def live_routing_confirmed() -> bool:
    """Secondary confirm — prevents accidental live routing in shared envs."""
    raw = os.getenv("HIBS_RACING_CONFIRM_LIVE", "").strip().lower()
    return raw in ("1", "true", "yes", "on") or raw == "yes"


def execution_disabled() -> bool:
    """False only when both live-routing env gates are armed."""
    return not (live_routing_allowed() and live_routing_confirmed())


def __getattr__(name: str):
    if name == "EXECUTION_DISABLED":
        return execution_disabled()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def betfair_enabled(cfg: dict | None = None) -> bool:
    """True when Betfair monetization is armed (credentials + enable flag)."""
    from hibs_racing.utils.monetization import betfair_monetization_armed

    if execution_disabled():
        return False
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
    disabled = execution_disabled()
    return {
        "disabled": disabled,
        "mode": "analytics" if disabled else "live",
        "message": EXECUTION_DISABLED_MSG if disabled else "",
        "dry_run": disabled,
        "live_routing_allowed": live_routing_allowed(),
        "live_routing_confirmed": live_routing_confirmed(),
        "betfair_enabled": betfair_enabled(cfg),
        "betfair_configured": betfair_configured(),
        "preferred_venues": preferred_execution_venues(cfg),
        "max_stake": 0.0 if disabled else float(os.getenv("HIBS_RACING_MAX_STAKE", "0") or 0),
        "sub_100ms_exchange": not disabled,
        "co_location": False,
        "institutional_note": (
            "Sub-100ms exchange execution not in analytics license (execution env gates)."
            if disabled
            else "Live routing armed — verify stake caps and compliance sign-off."
        ),
    }
