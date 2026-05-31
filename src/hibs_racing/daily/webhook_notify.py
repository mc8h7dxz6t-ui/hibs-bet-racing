"""Optional Telegram / Discord webhook for 06:00 daily digest."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any

from hibs_racing.daily.smart_picks import build_morning_smart_picks, format_digest_message


def webhook_configured() -> bool:
    return bool(
        (os.environ.get("TELEGRAM_BOT_TOKEN", "").strip() and os.environ.get("TELEGRAM_CHAT_ID", "").strip())
        or os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    )


def _post_json(url: str, payload: dict[str, Any], *, timeout: int = 20) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "hibs-racing/0.1"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")
        return {"status": resp.status, "body": body[:500]}


def send_telegram(text: str) -> dict[str, Any]:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        return {"ok": False, "skipped": True, "channel": "telegram"}
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text, "disable_web_page_preview": True}
    try:
        result = _post_json(url, payload)
        return {"ok": True, "channel": "telegram", **result}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "channel": "telegram", "error": str(exc), "status": exc.code}
    except OSError as exc:
        return {"ok": False, "channel": "telegram", "error": str(exc)}


def send_discord(text: str) -> dict[str, Any]:
    url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        return {"ok": False, "skipped": True, "channel": "discord"}
    payload = {"content": text[:2000]}
    try:
        result = _post_json(url, payload)
        return {"ok": True, "channel": "discord", **result}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "channel": "discord", "error": str(exc), "status": exc.code}
    except OSError as exc:
        return {"ok": False, "channel": "discord", "error": str(exc)}


def notify_daily_digest(*, limit: int = 3) -> dict[str, Any]:
    """Build Smart Portfolio digest and post to configured webhooks."""
    if not webhook_configured():
        return {"ok": False, "skipped": True, "reason": "Set TELEGRAM_BOT_TOKEN+TELEGRAM_CHAT_ID and/or DISCORD_WEBHOOK_URL"}

    payload = build_morning_smart_picks(limit=limit)
    text = format_digest_message(payload)
    results: list[dict[str, Any]] = []

    tg = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if tg:
        results.append(send_telegram(text))
    dc = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if dc:
        results.append(send_discord(text))

    ok = any(r.get("ok") for r in results)
    return {
        "ok": ok,
        "pick_count": payload.get("pick_count"),
        "message_preview": text[:400],
        "channels": results,
    }
