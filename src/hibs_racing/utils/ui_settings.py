"""Browser-managed monetization / webhook overrides (JSON file — no DB schema)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from hibs_racing.config import ROOT

SETTINGS_PATH = ROOT / "data" / "ui_monetization.json"

MONETIZATION_FIELDS: tuple[tuple[str, str, bool], ...] = (
    ("HIBS_AFFILIATE_VENUE", "Affiliate venue (matchbook | betfair | smarkets | betdaq)", False),
    ("HIBS_AFFILIATE_UTM_SOURCE", "UTM source tag on partner links", False),
    ("HIBS_AFFILIATE_TRACKING_ID", "Matchbook / partner tracking ID", False),
    ("HIBS_BETFAIR_MONETIZATION_ENABLED", "Enable Betfair monetization once account is ready (0|1)", False),
    ("AFFILIATE_MATCHBOOK_BASE_URL", "Matchbook affiliate landing URL", False),
    ("AFFILIATE_BETFAIR_BASE_URL", "Betfair affiliate landing URL", False),
    ("AFFILIATE_SMARKETS_BASE_URL", "Smarkets affiliate landing URL", False),
    ("AFFILIATE_BETDAQ_BASE_URL", "Betdaq affiliate landing URL", False),
    ("BETFAIR_APP_KEY", "Betfair app key (required when Betfair armed)", False),
    ("BETFAIR_USERNAME", "Betfair username", False),
    ("BETFAIR_PASSWORD", "Betfair password", True),
    ("MATCHBOOK_USERNAME", "Matchbook API username", True),
    ("MATCHBOOK_PASSWORD", "Matchbook API password", True),
    ("TELEGRAM_BOT_TOKEN", "Telegram bot token (06:01 digest)", True),
    ("TELEGRAM_CHAT_ID", "Telegram chat / channel ID", False),
    ("DISCORD_WEBHOOK_URL", "Discord webhook URL", True),
)


def load_ui_monetization() -> dict[str, str]:
    if not SETTINGS_PATH.exists():
        return {}
    try:
        raw = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    return {str(k): str(v) for k, v in raw.items() if v is not None and str(v).strip()}


def save_ui_monetization(values: dict[str, Any]) -> dict[str, str]:
    allowed = {key for key, _, _ in MONETIZATION_FIELDS}
    current = load_ui_monetization()
    merged = dict(current)
    for key, val in values.items():
        if key not in allowed:
            continue
        text = str(val or "").strip()
        if text:
            merged[key] = text
        elif key in merged:
            del merged[key]
    SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_PATH.write_text(json.dumps(merged, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    apply_saved_ui_env(merged)
    return merged


def apply_saved_ui_env(saved: dict[str, str] | None = None) -> None:
    """Overlay saved UI credentials onto process env (does not touch .env file)."""
    data = saved if saved is not None else load_ui_monetization()
    for key, val in data.items():
        if val:
            os.environ[key] = val


def _mask_secret(value: str) -> str:
    if not value:
        return ""
    if len(value) <= 6:
        return "••••••"
    return value[:3] + "••••" + value[-2:]


def monetization_form_payload(*, include_secrets: bool = False) -> dict[str, Any]:
    saved = load_ui_monetization()
    fields: list[dict[str, Any]] = []
    for key, label, secret in MONETIZATION_FIELDS:
        env_val = os.environ.get(key, "").strip()
        saved_val = saved.get(key, "").strip()
        effective = saved_val or env_val
        display = effective
        if secret and effective and not include_secrets:
            display = _mask_secret(effective)
        fields.append(
            {
                "key": key,
                "label": label,
                "secret": secret,
                "value": display if include_secrets else (saved_val or ("" if secret and env_val else env_val)),
                "effective_set": bool(effective),
                "source": "ui" if saved_val else ("env" if env_val else "unset"),
            }
        )
    return {
        "ok": True,
        "fields": fields,
        "settings_path": str(SETTINGS_PATH),
        "saved_keys": sorted(saved.keys()),
    }
