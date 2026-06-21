"""Read-only Inst++ racing health — HTTP probe of hibs-racing only (sale-safe).

No SQLite or filesystem reads into hibs-racing data dirs. Football probes
``HIBS_RACING_BASE_URL`` / loopback ``/api/health?full=1`` for R5–R7 fields.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

_INST_PP_LAYER = "institutional_plus_plus_racing"


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def evidence_deploy_since_iso() -> Optional[str]:
    explicit = (os.getenv("HIBS_RACING_EVIDENCE_DEPLOY_DATE") or "").strip()
    if not explicit:
        explicit = (os.getenv("HIBS_EVIDENCE_DEPLOY_DATE") or "").strip()
    if not explicit:
        return None
    if "T" not in explicit:
        explicit = f"{explicit}T00:00:00+00:00"
    return explicit


def racing_health_url(*, full: bool = True) -> str:
    """Resolve racing /api/health URL (co-hosted loopback or public base)."""
    explicit = (os.getenv("HIBS_RACING_LOCAL_HEALTH_URL") or "").strip().rstrip("/")
    if explicit:
        base = explicit if explicit.endswith("/api/health") else f"{explicit}/api/health"
    else:
        from hibs_predictor.product_links import racing_base_url

        root = racing_base_url().rstrip("/")
        local_flag = (os.getenv("HIBS_RACING_EVIDENCE_LOCAL") or "").strip().lower()
        racing_deploy = (os.getenv("HIBS_RACING_DEPLOY_PATH") or "/opt/hibs-racing").strip()
        if local_flag in ("1", "true", "yes", "on") or (
            root.startswith("/") and os.path.isdir(racing_deploy)
        ):
            root = "http://127.0.0.1:5003"
        elif root.startswith("/"):
            public = (os.getenv("HIBS_PRODUCTION_URL") or "https://hibs-bet.co.uk").rstrip("/")
            root = f"{public}{root}"
        base = f"{root}/api/health"
    if full and "full=" not in base:
        sep = "&" if "?" in base else "?"
        base = f"{base}{sep}full=1"
    return base


def _http_get_json(url: str, *, timeout: float = 20.0) -> Tuple[int, Dict[str, Any]]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hibs-bet-racing-inst-health/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
            return int(resp.status), data if isinstance(data, dict) else {}
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
            data = json.loads(body) if body.strip() else {}
        except Exception:
            data = {}
        return int(exc.code), data if isinstance(data, dict) else {}
    except Exception as exc:
        return 0, {"error": str(exc)[:160]}


def fetch_upstream_racing_health(*, full: bool = True) -> Tuple[int, Dict[str, Any]]:
    url = racing_health_url(full=full)
    timeout = float(os.getenv("HIBS_RACING_EVIDENCE_TIMEOUT_HEALTH", "30"))
    return _http_get_json(url, timeout=timeout)


def _dig(data: Any, *path: str) -> Any:
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _coverage_from_health(health: Dict[str, Any]) -> Optional[float]:
    for path in (
        ("telemetry_balance", "coverage_pct"),
        ("snapshot_coverage_pct",),
        ("coverage_pct",),
    ):
        val = _dig(health, *path)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _paper_rows_from_health(health: Dict[str, Any]) -> Optional[int]:
    for path in (
        ("paper", "n_rows"),
        ("paper", "settled"),
        ("paper_rows",),
    ):
        val = _dig(health, *path)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


def _derive_recon_clean(health: Dict[str, Any]) -> Optional[bool]:
    for key in ("recon_clean", "paper_recon_clean"):
        if key in health and health[key] is not None:
            return bool(health[key])
    nan_ok = health.get("nan_integrity_passed")
    sync = health.get("db_ui_in_sync")
    unscored = health.get("unscored_runners")
    if nan_ok is False or sync is False:
        return False
    if unscored is not None and int(unscored) > 0:
        return False
    if health.get("runners_loaded") and health.get("scores_loaded") is not None:
        if int(unscored or 0) == 0 and int(health.get("runners_loaded") or 0) > 0:
            return True
    return None


def normalize_racing_health(health: Dict[str, Any]) -> Dict[str, Any]:
    """Derive Inst++ headline fields from hibs-racing /api/health JSON only."""
    merged = dict(health)
    cov = _coverage_from_health(merged)
    tel = merged.get("telemetry_balance")
    if not isinstance(tel, dict):
        tel = {}
    if cov is not None:
        tel = {**tel, "coverage_pct": cov}
        merged["telemetry_balance"] = tel

    recon = _derive_recon_clean(merged)
    if recon is not None and "recon_clean" not in merged:
        merged["recon_clean"] = recon

    paper = merged.get("paper")
    if not isinstance(paper, dict):
        paper = {}
    n_rows = _paper_rows_from_health(merged)
    if n_rows is not None:
        paper = {**paper, "n_rows": n_rows}
        merged["paper"] = paper

    return merged


def _merge_health(primary: Dict[str, Any], fallback: Dict[str, Any]) -> Dict[str, Any]:
    """Primary wins when present; fallback fills R5–R7 gaps only (both HTTP payloads)."""
    if not fallback:
        return normalize_racing_health(primary)
    if not primary:
        return normalize_racing_health(fallback)

    fb_norm = normalize_racing_health(fallback)
    merged = dict(fb_norm)
    for key, val in primary.items():
        if val is not None:
            merged[key] = val

    tel_p = primary.get("telemetry_balance") if isinstance(primary.get("telemetry_balance"), dict) else {}
    tel_f = fb_norm.get("telemetry_balance") if isinstance(fb_norm.get("telemetry_balance"), dict) else {}
    cov_p = _dig(tel_p, "coverage_pct") or primary.get("snapshot_coverage_pct")
    cov_f = _dig(tel_f, "coverage_pct") or fb_norm.get("snapshot_coverage_pct")
    cov = cov_p if cov_p is not None else cov_f
    if cov is not None:
        merged["telemetry_balance"] = {**tel_f, **tel_p, "coverage_pct": float(cov)}

    recon_p = _derive_recon_clean(primary)
    recon = recon_p if recon_p is not None else _derive_recon_clean(fb_norm)
    if recon is not None:
        merged["recon_clean"] = recon

    paper_p = primary.get("paper") if isinstance(primary.get("paper"), dict) else {}
    paper_f = fb_norm.get("paper") if isinstance(fb_norm.get("paper"), dict) else {}
    n_p = _paper_rows_from_health(primary)
    n_f = _paper_rows_from_health(fb_norm)
    n_rows = n_p if n_p is not None else n_f
    if n_rows is not None:
        merged["paper"] = {**paper_f, **paper_p, "n_rows": n_rows}

    return merged


def build_institutional_racing_health() -> Dict[str, Any]:
    """Inst++ racing health for /api/inst-pp/racing/health — HTTP-only."""
    status, upstream = fetch_upstream_racing_health(full=True)
    merged = normalize_racing_health(upstream if status == 200 else {})

    return {
        "inst_pp_layer": _INST_PP_LAYER,
        "checked_at": _utc_iso(),
        "since_deploy_iso": evidence_deploy_since_iso(),
        "sources": {
            "upstream_status": status,
            "upstream_url": racing_health_url(full=True),
            "integration": "http_only",
        },
        "ok": status == 200,
        **merged,
    }
