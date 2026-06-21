"""Read-only FVE / line-trader health — cached probe, no book API calls from hibs-bet."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Tuple
from urllib import error, request


_CACHE: Dict[str, Any] = {"t": 0.0, "payload": None}
_TTL_SEC = float(os.getenv("HIBS_FVE_STATUS_TTL_SEC", "12"))


def fve_api_base_url() -> str:
    return (os.getenv("FVE_API_URL") or "http://127.0.0.1:8010").rstrip("/")


def fve_public_ws_base() -> str:
    explicit = (os.getenv("HIBS_FVE_PUBLIC_WS_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    public = (os.getenv("HIBS_FVE_PUBLIC_API_URL") or "").strip().rstrip("/")
    if public:
        return public.replace("https://", "wss://").replace("http://", "ws://")
    return fve_api_base_url().replace("https://", "wss://").replace("http://", "ws://")


def line_trader_page_url() -> str:
    return (os.getenv("HIBS_LINE_TRADER_URL") or "/line-trader").strip() or "/line-trader"


def fve_integration_enabled() -> bool:
    return (os.getenv("HIBS_FVE_INTEGRATION") or "").strip().lower() in ("1", "true", "yes", "on")


def _http_json(url: str, *, timeout: float = 4.0) -> Tuple[bool, Dict[str, Any], str | None]:
    try:
        req = request.Request(url, headers={"User-Agent": "hibs-bet-fve-status/1.0", "Accept": "application/json"})
        with request.urlopen(req, timeout=timeout) as resp:
            import json

            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
            return True, data if isinstance(data, dict) else {}, None
    except error.HTTPError as exc:
        return False, {}, f"http_{exc.code}"
    except Exception as exc:
        return False, {}, str(exc)[:120]


def fetch_fve_status(*, force: bool = False) -> Dict[str, Any]:
    """Probe FVE /health with short TTL — safe for dashboard polls."""
    now = time.monotonic()
    if (
        not force
        and _CACHE["payload"] is not None
        and (now - float(_CACHE["t"])) < _TTL_SEC
    ):
        return dict(_CACHE["payload"])

    base = fve_api_base_url()
    ok, health, err = _http_json(f"{base}/health")
    worker = health.get("worker") if isinstance(health.get("worker"), dict) else {}
    worker_live = bool(worker.get("alive")) if ok else False
    force = (os.getenv("HIBS_FVE_FORCE_PAUSED") or "").strip().lower()
    if force in ("1", "true", "yes", "on"):
        paused = True
    elif force in ("0", "false", "no", "off"):
        paused = False
    elif ok:
        paused = bool(health.get("paused")) if "paused" in health else not worker_live
    else:
        paused = True
    budgets = (health.get("api_budgets") or {}).get("sources") or {} if ok else {}
    exhausted = [
        name
        for name, row in budgets.items()
        if isinstance(row, dict) and int(row.get("remaining") or 0) <= 0
    ]
    ws = health.get("ws") if isinstance(health.get("ws"), dict) else {}
    backtest_slice = health.get("backtest_slice") if isinstance(health.get("backtest_slice"), dict) else {}
    audit_ops = health.get("audit_ops") if isinstance(health.get("audit_ops"), dict) else {}
    inplay_evidence = health.get("inplay_evidence") if isinstance(health.get("inplay_evidence"), dict) else {}
    payload = {
        "integration_enabled": fve_integration_enabled(),
        "paused": paused,
        "worker_live": worker_live,
        "api_url": base,
        "ws_base": fve_public_ws_base(),
        "line_trader_url": line_trader_page_url(),
        "reachable": ok,
        "error": err,
        "status": health.get("status") if ok else None,
        "feed_mode": health.get("feed_mode"),
        "line_bus": health.get("line_bus"),
        "cache_backend": health.get("cache_backend"),
        "worker": worker,
        "budgets_exhausted": exhausted,
        "ws_clients": ws.get("active_clients"),
        "ws_backpressure_drops": ws.get("backpressure_drops"),
        "backtest_slice": backtest_slice,
        "audit_ops": audit_ops,
        "inplay_evidence": inplay_evidence,
    }
    _CACHE["t"] = now
    _CACHE["payload"] = payload
    return dict(payload)
