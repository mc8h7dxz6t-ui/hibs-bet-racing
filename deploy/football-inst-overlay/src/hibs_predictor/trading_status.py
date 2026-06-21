"""Read-only Harvested Execution status: metrics, Alpaca portfolio, performance narrative."""

from __future__ import annotations

import os
import re
from decimal import Decimal, InvalidOperation
from typing import Any

import requests

from hibs_predictor.evidence_presentation import buyer_readiness_bundle, trading_safety_layers
from hibs_predictor.trading_revenue import build_promotion_bundle, infer_phase
from hibs_predictor.trading_symbols import is_crypto_symbol, parse_symbol_list

_METRIC_LINE = re.compile(
    r"^(?P<name>[a-zA-Z_:][a-zA-Z0-9_:]*)\s+(?P<value>-?\d+(?:\.\d+)?(?:e[+-]?\d+)?)$"
)

_METRIC_KEYS = (
    "trading_node_ready",
    "trading_stale_feed_ms",
    "trading_reconciliation_drifts_total",
    "trading_reconciliation_runs_total",
    "trading_strategy_routed_total",
    "trading_strategy_scan_cycles_total",
    "trading_strategy_no_signal_total",
    "trading_strategy_gate_block_total",
    "trading_strategy_risk_reject_total",
    "trading_stream_errors_total",
    "trading_stream_messages_total",
    "trading_stale_feed_equity_ms",
    "trading_stale_feed_crypto_ms",
    "trading_stream_messages_equity_total",
    "trading_stream_messages_crypto_total",
    "trading_healthy_cycles_total",
)


def trading_metrics_base_url() -> str:
    return os.getenv("TRADING_METRICS_URL", "http://127.0.0.1:9109").rstrip("/")


def crypto_enabled() -> bool:
    return os.getenv("TRADING_ENABLE_CRYPTO", "").strip().lower() in ("1", "true", "yes")


def configured_symbols() -> dict[str, Any]:
    equity = parse_symbol_list(os.getenv("STRATEGY_SYMBOLS", "AAPL,TSLA"))
    crypto = parse_symbol_list(os.getenv("STRATEGY_CRYPTO_SYMBOLS", ""))
    if not crypto_enabled():
        crypto = ()
    return {
        "equity": list(equity),
        "crypto": list(crypto),
        "crypto_enabled": crypto_enabled() and bool(crypto),
        "stream_feed": os.getenv("MARKET_STREAM_FEED", "iex"),
        "profile": os.getenv("TRADING_PROFILE", "conservative"),
        "phase": os.getenv("TRADING_DEPLOYMENT_PHASE", "paper"),
    }


def parse_prometheus_text(body: str) -> dict[str, float]:
    out: dict[str, float] = {}
    for line in body.splitlines():
        if not line or line.startswith("#"):
            continue
        match = _METRIC_LINE.match(line.strip())
        if match:
            out[match.group("name")] = float(match.group("value"))
    return out


def _alpaca_headers() -> dict[str, str] | None:
    key = os.getenv("ALPACA_API_KEY", "").strip()
    secret = os.getenv("ALPACA_API_SECRET", "").strip()
    if not key or not secret:
        return None
    return {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Content-Type": "application/json",
    }


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def fetch_alpaca_portfolio(*, timeout: float = 5.0) -> dict[str, Any]:
    headers = _alpaca_headers()
    base = os.getenv("ALPACA_BASE_URL", "https://paper-api.alpaca.markets").rstrip("/")
    out: dict[str, Any] = {
        "available": False,
        "error": None,
        "account": {},
        "equity_positions": [],
        "crypto_positions": [],
        "performance": {},
    }
    if not headers:
        out["error"] = "ALPACA_API_KEY/SECRET not set in environment"
        return out

    try:
        acct = requests.get(f"{base}/v2/account", headers=headers, timeout=timeout)
        acct.raise_for_status()
        account = acct.json()
        pos = requests.get(f"{base}/v2/positions", headers=headers, timeout=timeout)
        pos.raise_for_status()
        positions = pos.json() if isinstance(pos.json(), list) else []

        equity_val = _dec(account.get("equity"))
        last_equity = _dec(account.get("last_equity"))
        day_pnl = None
        day_pnl_pct = None
        if equity_val is not None and last_equity is not None and last_equity != 0:
            day_pnl = equity_val - last_equity
            day_pnl_pct = (day_pnl / last_equity) * Decimal("100")

        out["available"] = True
        out["account"] = {
            "status": account.get("status"),
            "equity": str(equity_val) if equity_val is not None else None,
            "cash": account.get("cash"),
            "buying_power": account.get("buying_power"),
            "portfolio_value": account.get("portfolio_value"),
            "day_pnl": str(day_pnl) if day_pnl is not None else None,
            "day_pnl_pct": str(round(day_pnl_pct, 4)) if day_pnl_pct is not None else None,
            "paper": str(account.get("account_number", "")).startswith("PA") or True,
        }
        out["performance"] = {
            "equity": out["account"]["equity"],
            "day_pnl": out["account"]["day_pnl"],
            "day_pnl_pct": out["account"]["day_pnl_pct"],
            "buying_power": out["account"]["buying_power"],
        }

        for p in positions:
            sym = str(p.get("symbol", ""))
            row = {
                "symbol": sym,
                "qty": p.get("qty"),
                "market_value": p.get("market_value"),
                "unrealized_pl": p.get("unrealized_pl"),
                "unrealized_plpc": p.get("unrealized_plpc"),
                "asset_class": p.get("asset_class"),
            }
            if is_crypto_symbol(sym) or str(p.get("asset_class", "")).lower() == "crypto":
                out["crypto_positions"].append(row)
            else:
                out["equity_positions"].append(row)
    except Exception as exc:
        out["error"] = str(exc)
    return out


def build_dashboard_insights(
    *,
    online: bool,
    metrics: dict[str, float | None],
    portfolio: dict[str, Any],
    config: dict[str, Any],
    ready_text: str = "",
) -> list[dict[str, str]]:
    """Plain-English cards for the trader-style dashboard."""
    drifts = metrics.get("trading_reconciliation_drifts_total") or 0
    routed = metrics.get("trading_strategy_routed_total") or 0
    scans = metrics.get("trading_strategy_scan_cycles_total") or 0
    no_sig = metrics.get("trading_strategy_no_signal_total") or 0
    stale = metrics.get("trading_stale_feed_ms")
    stream_err = metrics.get("trading_stream_errors_total") or 0

    insights: list[dict[str, str]] = []

    if online:
        insights.append(
            {
                "tone": "ok",
                "title": "System health",
                "body": "Execution node is NODE_READY: reconciliation, risk, and metrics are live.",
            }
        )
    else:
        detail = (ready_text or "").strip()
        if detail.startswith("NODE_UNREADY:"):
            detail = detail[len("NODE_UNREADY:") :].strip()
        body = "Node is not ready."
        if detail:
            if "stale_feed" in detail:
                body += (
                    f" Reason: {detail}. "
                    "Off US market hours this is normal for shadow (stream on :9108). "
                    "Paper without stream (beside shadow) should clear after redeploy."
                )
            elif detail == "boot_barrier_unarmed":
                body += " Still booting — wait 1–2 minutes after restart."
            else:
                body += f" Reason: {detail}."
        else:
            body += " Check VPS trading-paper / trading-shadow-soak or TRADING_METRICS_URL in football .env."
        insights.append(
            {
                "tone": "bad",
                "title": "System health",
                "body": body,
            }
        )

    if drifts == 0:
        insights.append(
            {
                "tone": "ok",
                "title": "Ledger vs broker",
                "body": "No reconciliation drifts — internal books match Alpaca paper.",
            }
        )
    else:
        insights.append(
            {
                "tone": "bad",
                "title": "Ledger vs broker",
                "body": f"{int(drifts)} drift(s) detected. Trading should halt until resolved.",
            }
        )

    perf = portfolio.get("performance") or {}
    if perf.get("day_pnl_pct"):
        tone = "ok" if float(perf["day_pnl_pct"]) >= 0 else "warn"
        insights.append(
            {
                "tone": tone,
                "title": "Today's paper P&L",
                "body": f"{perf.get('day_pnl', '—')} ({perf.get('day_pnl_pct', '—')}%) on equity "
                f"{perf.get('equity', '—')}. Paper only — not live capital.",
            }
        )

    if scans > 0:
        hit_rate = (routed / scans * 100) if scans else 0
        insights.append(
            {
                "tone": "ok" if routed == 0 else "warn",
                "title": "Strategy activity",
                "body": f"{int(scans)} scans, {int(routed)} orders routed, {int(no_sig)} no-signal. "
                f"Conservative OFI gates ({config.get('profile', 'conservative')}) keep hit rate low (~{hit_rate:.1f}% routed).",
            }
        )

    if stale is not None and stale > 5000:
        insights.append(
            {
                "tone": "warn",
                "title": "Market data",
                "body": f"Feed stale {int(stale)}ms — stream may be down or VPS holds the only WSS slot.",
            }
        )
    elif stream_err > 0:
        insights.append(
            {
                "tone": "warn",
                "title": "Market data",
                "body": f"{int(stream_err)} stream error(s). If Mac+VPS both subscribed, use one stream only.",
            }
        )
    else:
        insights.append(
            {
                "tone": "ok",
                "title": "Market data",
                "body": "Stream errors low and feed fresh enough for readiness checks.",
            }
        )

    if config.get("crypto_enabled"):
        n = len(portfolio.get("crypto_positions") or [])
        insights.append(
            {
                "tone": "ok",
                "title": "Crypto lane",
                "body": f"Crypto enabled for {', '.join(config.get('crypto') or [])}. "
                f"{n} open crypto position(s) on paper.",
            }
        )
    else:
        insights.append(
            {
                "tone": "ok",
                "title": "Crypto lane",
                "body": "Equities only. Set TRADING_ENABLE_CRYPTO=1 and STRATEGY_CRYPTO_SYMBOLS=BTC/USD,ETH/USD to run alongside.",
            }
        )

    return insights


def fetch_trading_status(*, timeout: float = 3.0) -> dict[str, Any]:
    base = trading_metrics_base_url()
    config = configured_symbols()
    result: dict[str, Any] = {
        "metrics_url": base,
        "ready": None,
        "ready_text": "",
        "online": False,
        "error": None,
        "metrics": {},
        "config": config,
        "portfolio": fetch_alpaca_portfolio(timeout=timeout),
        "insights": [],
    }
    try:
        ready_resp = requests.get(f"{base}/ready", timeout=timeout)
        result["ready"] = ready_resp.status_code
        result["ready_text"] = (ready_resp.text or "").strip()[:200]
        result["online"] = ready_resp.status_code == 200 and "NODE_READY" in (ready_resp.text or "")
        metrics_resp = requests.get(f"{base}/metrics", timeout=timeout)
        metrics_resp.raise_for_status()
        parsed = parse_prometheus_text(metrics_resp.text)
        result["metrics"] = {k: parsed.get(k) for k in _METRIC_KEYS if k in parsed}
        result["insights"] = build_dashboard_insights(
            online=result["online"],
            metrics=result["metrics"],
            portfolio=result["portfolio"],
            config=config,
            ready_text=result["ready_text"],
        )
        revenue, promotion = build_promotion_bundle(
            metrics_url=base,
            env_phase=str(config.get("phase") or ""),
            portfolio=result["portfolio"],
            online=result["online"],
        )
        result["revenue"] = revenue
        result["promotion"] = {
            k: promotion[k]
            for k in (
                "tier",
                "tier_label",
                "score",
                "next_action",
                "active_transition",
                "clean_shadow_days",
                "clean_shadow_days_required",
                "manifest_days_total",
                "shadow_to_micro",
                "micro_to_live",
                "error",
            )
            if k in promotion
        }
        phase = infer_phase(metrics_url=base, env_phase=str(config.get("phase") or ""))
        safety = trading_safety_layers(
            metrics=result["metrics"],
            phase=phase,
            clean_shadow_days=promotion.get("clean_shadow_days"),
            clean_shadow_required=promotion.get("clean_shadow_days_required"),
            shadow_to_micro_passed=(promotion.get("shadow_to_micro") or {}).get("passed"),
        )
        inv_pass = all(i.get("pass") for i in safety.get("invariants") or [])
        readiness = buyer_readiness_bundle(
            gates=safety.get("invariants") or [],
            critical_pass=inv_pass,
            evidence_pass=bool(result["online"]),
            vertical="trading",
        )
        result["safety_layers"] = safety
        result["commercial_tier"] = promotion.get("tier") or readiness.get("commercial_tier")
        result["buyer_readiness_score"] = promotion.get("score") or readiness.get("buyer_readiness_score")
    except Exception as exc:
        result["error"] = str(exc)
        try:
            revenue, promotion = build_promotion_bundle(
                metrics_url=base,
                env_phase=str(config.get("phase") or ""),
                portfolio=result["portfolio"],
                online=False,
            )
            result["revenue"] = revenue
            result["promotion"] = {
                k: promotion[k]
                for k in (
                    "tier",
                    "tier_label",
                    "score",
                    "next_action",
                    "active_transition",
                    "clean_shadow_days",
                    "clean_shadow_days_required",
                    "shadow_to_micro",
                    "micro_to_live",
                )
                if k in promotion
            }
        except Exception:
            pass
        result["insights"] = build_dashboard_insights(
            online=False,
            metrics={},
            portfolio=result["portfolio"],
            config=config,
            ready_text=result.get("ready_text", ""),
        )
    return result
