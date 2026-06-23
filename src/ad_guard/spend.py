"""Spend metric extraction — JSON path parsers per marketing API provider."""

from __future__ import annotations

import re
from typing import Any

# Provider-specific JSON paths (laser-focused — extend per buyer contract)
_PROVIDER_PATHS: dict[str, dict[str, tuple[str, ...]]] = {
    "google": {
        "campaign_id": ("campaignId", "campaign_id", "campaign"),
        "bid_micros": ("bidMicros", "bid_micros", "cpcBidMicros"),
        "spend_micros": ("costMicros", "cost_micros", "amountMicros"),
    },
    "meta": {
        "campaign_id": ("campaign_id", "campaignId", "id"),
        "bid_amount": ("bid_amount", "daily_budget", "lifetime_budget"),
        "spend_delta": ("spend", "amount_spent"),
    },
    "generic": {
        "campaign_id": ("campaign_id", "campaignId"),
        "bid_amount": ("bid_amount", "bid", "cpc"),
        "spend_delta": ("spend_delta", "spend", "amount"),
    },
}

_CAMPAIGN_RESOURCE_RE = re.compile(r"campaigns/(\d+)")


def _dig(body: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        current: Any = body
        if "." in key:
            for part in key.split("."):
                if isinstance(current, dict) and part in current:
                    current = current[part]
                else:
                    current = None
                    break
            if current is not None:
                return current
            continue
        if isinstance(current, dict) and key in current:
            return current[key]
    return None


def _normalize_micros(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value) / 1_000_000.0
    except (TypeError, ValueError):
        return None


def _normalize_amount(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _campaign_from_resource_name(body: dict[str, Any]) -> str | None:
    for key in ("resourceName", "campaign", "campaignResourceName"):
        raw = body.get(key)
        if isinstance(raw, str):
            match = _CAMPAIGN_RESOURCE_RE.search(raw)
            if match:
                return match.group(1)
    return None


def extract_spend_metrics(
    body: dict[str, Any],
    *,
    provider: str = "generic",
) -> tuple[str, float | None, float | None]:
    """
    Return (campaign_id, bid_amount, spend_delta) from outbound API body.

    bid_amount and spend_delta may be None when not present — Z-score gate skips.
    """
    paths = _PROVIDER_PATHS.get(provider, _PROVIDER_PATHS["generic"])
    campaign_id = _dig(body, *paths["campaign_id"])
    if campaign_id is None:
        campaign_id = _campaign_from_resource_name(body)
    campaign_id = str(campaign_id or "unknown")

    bid_amount: float | None = None
    spend_delta: float | None = None

    if provider == "google":
        bid_amount = _normalize_micros(_dig(body, *paths.get("bid_micros", ())))
        spend_delta = _normalize_micros(_dig(body, *paths.get("spend_micros", ())))
    else:
        bid_paths = paths.get("bid_amount", ())
        spend_paths = paths.get("spend_delta", ())
        bid_amount = _normalize_amount(_dig(body, *bid_paths)) if bid_paths else None
        spend_delta = _normalize_amount(_dig(body, *spend_paths)) if spend_paths else None

    return campaign_id, bid_amount, spend_delta
