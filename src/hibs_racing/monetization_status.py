"""Racing monetization status — mirror football /api/monetization/status contract."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

MonetizationMode = Literal["affiliate", "paper", "micro", "live", "sale_gated"]


def _env_truthy(name: str) -> bool:
    import os

    return (os.getenv(name) or "").strip().lower() in ("1", "true", "yes", "on")


def _resolve_racing_mode() -> MonetizationMode:
    if _env_truthy("HIBS_LIVE_TRADING_ENABLED") or _env_truthy("HIBS_EXECUTION_LIVE"):
        if _env_truthy("HIBS_RACING_MICRO_CAP_GBP") or _env_truthy("HIBS_EXECUTION_MAX_STAKE_GBP"):
            return "micro"
        return "live"
    from hibs_racing.utils.monetization import active_venues

    if active_venues():
        return "affiliate"
    return "paper"


def build_monetization_status() -> dict[str, Any]:
    from hibs_racing.utils.monetization import public_monetization_payload

    mode = _resolve_racing_mode()
    venues = public_monetization_payload()
    return {
        "schema": "hibs_monetization_status_v1",
        "checked_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "affiliate_active": bool(venues.get("active_venues")),
        "verticals": {
            "football": "paper",
            "racing": mode,
            "trading": "paper",
            "inplay": "paper",
        },
        "lanes": {
            "football": "paper",
            "racing": mode,
            "trading": "paper",
            "inplay": "paper",
            "lines": "paper",
        },
        "operator_live": {
            "execution_live": _env_truthy("HIBS_EXECUTION_LIVE"),
            "live_trading_enabled": _env_truthy("HIBS_LIVE_TRADING_ENABLED"),
        },
        "venues": venues,
        "notes": {
            "affiliate": "Click-out via monetized_link on picks",
            "paper": "Paper ledger + execution pass dry-run",
            "micro": "Operator micro lane with stake caps",
            "live": "Live exchange submit armed",
        },
    }
