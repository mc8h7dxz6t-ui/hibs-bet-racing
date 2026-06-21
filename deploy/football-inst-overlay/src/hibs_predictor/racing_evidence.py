"""Racing institutional evidence gates — probes hibs-racing HTTP API (separate repo)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.evidence_presentation import buyer_readiness_bundle, gate_row

# Mirrors MASTER_OPERATIONS_SCORECARD §3 telemetry thresholds
COVERAGE_PASS_OBS_PCT = 35.0
COVERAGE_PASS_PROD_PCT = 50.0
MIN_PAPER_ROWS = 25


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _racing_base_url() -> str:
    explicit = (os.getenv("HIBS_RACING_PUBLIC_URL") or "").strip().rstrip("/")
    local_flag = (os.getenv("HIBS_RACING_EVIDENCE_LOCAL") or "").strip().lower()
    racing_root = (os.getenv("HIBS_RACING_DEPLOY_PATH") or "/opt/hibs-racing").strip()
    if local_flag in ("0", "false", "no", "off"):
        return explicit or "https://hibs-bet.co.uk/racing"
    # VPS co-host: always probe loopback for evidence (public /cards can timeout behind nginx)
    if local_flag in ("1", "true", "yes", "on") or os.path.isdir(racing_root):
        return "http://127.0.0.1:5003"
    return explicit or "https://hibs-bet.co.uk/racing"


def _http_timeout_for(url: str) -> float:
    if url.endswith("/cards"):
        return _env_float("HIBS_RACING_EVIDENCE_TIMEOUT_CARDS", 90.0)
    if url.endswith("/api/health"):
        return _env_float("HIBS_RACING_EVIDENCE_TIMEOUT_HEALTH", 30.0)
    if url.endswith("/api/ping"):
        return _env_float("HIBS_RACING_EVIDENCE_TIMEOUT_PING", 15.0)
    return _env_float("HIBS_RACING_EVIDENCE_TIMEOUT_DEFAULT", 20.0)


def _football_base_url() -> str:
    return (os.getenv("HIBS_PRODUCTION_URL") or "https://hibs-bet.co.uk").rstrip("/")


def _http_get(url: str, *, timeout: float = 8.0) -> Tuple[int, str]:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hibs-bet-racing-evidence/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.status), resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = str(exc)
        return int(exc.code), body
    except Exception as exc:
        return 0, str(exc)[:200]


def _parse_json(text: str) -> Dict[str, Any]:
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _dig(data: Any, *path: str) -> Any:
    cur = data
    for key in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _coverage_pct(health: Dict[str, Any]) -> Optional[float]:
    for path in (
        ("telemetry_balance", "coverage_pct"),
        ("telemetry", "coverage_pct"),
        ("audit_ops", "coverage_pct"),
        ("snapshot_coverage_pct",),
        ("coverage_pct",),
        ("racing", "coverage_pct"),
    ):
        val = _dig(health, *path)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _recon_clean(health: Dict[str, Any]) -> Optional[bool]:
    for path in (
        ("recon_clean",),
        ("paper_recon_clean",),
        ("institutional", "recon_clean"),
        ("reconciliation", "clean"),
        ("audit_ops", "recon_clean"),
    ):
        val = _dig(health, *path)
        if val is not None:
            return bool(val)
    inst = _dig(health, "institutional_check", "pass")
    if inst is not None:
        return bool(inst)
    return None


def _paper_row_count(health: Dict[str, Any]) -> Optional[int]:
    for path in (
        ("paper_rows",),
        ("paper", "n_rows"),
        ("ledger", "n_paper_picks"),
        ("audit_ops", "n_paper_rows"),
    ):
        val = _dig(health, *path)
        if val is not None:
            try:
                return int(val)
            except (TypeError, ValueError):
                continue
    return None


def _enrich_health_from_aggregator(health: Dict[str, Any]) -> Dict[str, Any]:
    """Fill R5–R7 gaps via HTTP full-health probe (no cross-repo SQLite)."""
    if (os.getenv("HIBS_RACING_INST_AGGREGATOR") or "1").strip().lower() in ("0", "false", "no", "off"):
        return health
    try:
        from hibs_predictor.racing_health_aggregator import _merge_health, fetch_upstream_racing_health

        status, full_health = fetch_upstream_racing_health(full=True)
        fallback = full_health if status == 200 else {}
        return _merge_health(health, fallback)
    except Exception:
        return health


def racing_evidence_gates_from_health(
    health: Dict[str, Any],
    *,
    probes: Dict[str, Any],
    base_url: str,
    ping_json: Optional[Dict[str, Any]] = None,
    health_ok: bool = True,
    ping_ok: bool = True,
    cards_ok: bool = True,
    cards_nonempty: bool = True,
    cards_body_len: int = 0,
    portfolio_ok: bool = True,
    port_code: int = 0,
    ping_code: int = 200,
    cards_code: int = 200,
    health_code: int = 200,
) -> Dict[str, Any]:
    """Build R1–R7 gates from a health dict (after Inst++ aggregator merge)."""
    health = _enrich_health_from_aggregator(health)
    coverage = _coverage_pct(health) if health_ok else None
    is_prod = (os.getenv("HIBS_PRODUCTION") or "").strip().lower() in ("1", "true", "yes", "on")
    cov_threshold = COVERAGE_PASS_PROD_PCT if is_prod else COVERAGE_PASS_OBS_PCT
    coverage_pass = coverage is not None and float(coverage) >= cov_threshold

    recon = _recon_clean(health) if health_ok else None
    recon_pass = recon is True

    paper_n = _paper_row_count(health) if health_ok else None
    paper_pass = paper_n is not None and paper_n >= MIN_PAPER_ROWS

    gates: List[Dict[str, Any]] = [
        gate_row(
            "R1_ping",
            label="Racing /api/ping",
            passed=ping_ok,
            actual=ping_code,
            threshold="200",
            message="Deploy hibs-racing + nginx /racing proxy",
            critical=True,
        ),
        gate_row(
            "R2_cards",
            label="Cards page reachable",
            passed=cards_ok,
            actual=cards_code,
            threshold="200|302",
            message="Run VPS daily_refresh or deploy_racing_data_to_vps.sh",
            critical=True,
        ),
        gate_row(
            "R2b_cards_data",
            label="Cards body non-empty",
            passed=cards_nonempty,
            actual=cards_body_len if cards_ok else 0,
            threshold=">800 bytes + card markup",
            message="feature_store.sqlite stale — VPS cron or Mac data sync",
            critical=True,
        ),
        gate_row(
            "R3_health",
            label="Racing /api/health",
            passed=health_ok,
            actual=health_code,
            threshold="200",
            message="Inst++ health via hibs-racing /api/health or /api/inst-pp/racing/health",
            critical=True,
        ),
        gate_row(
            "R4_portfolio_link",
            label="Football portfolio proxy",
            passed=portfolio_ok,
            actual=port_code,
            threshold="200|401",
            message="Set HIBS_PORTFOLIO_API_URL in football .env",
            critical=False,
        ),
        gate_row(
            "R5_coverage",
            label="Telemetry coverage",
            passed=coverage_pass if coverage is not None else False,
            actual=coverage,
            threshold=f">={cov_threshold}%",
            message="telemetry_balance.coverage_pct (upstream or Inst++ aggregator)",
            critical=False,
            window="telemetry",
            coverage_pct=float(coverage) if coverage is not None else None,
        ),
        gate_row(
            "R6_recon_clean",
            label="Paper recon clean",
            passed=recon_pass,
            actual=recon,
            threshold="true",
            message="daily_refresh institutional-check --require-recon-clean",
            critical=False,
            window="paper_recon",
        ),
        gate_row(
            "R7_paper_sample",
            label="Paper ledger sample",
            passed=paper_pass,
            actual=paper_n,
            threshold=f">={MIN_PAPER_ROWS} rows",
            message="Accumulate --paper picks via daily batch",
            critical=False,
            n=paper_n,
            window="ledger",
        ),
    ]

    critical = [g for g in gates if g.get("critical")]
    evidence = [g for g in gates if not g.get("critical")]
    critical_pass = all(g["pass"] for g in critical)
    evidence_pass = all(g["pass"] for g in evidence)
    passed = sum(1 for g in gates if g["pass"])
    ratio = passed / max(len(gates), 1)

    if not critical_pass:
        grade = "D"
    elif evidence_pass:
        grade = "A"
    elif ratio >= 0.85:
        grade = "B+"
    elif ratio >= 0.7:
        grade = "B"
    elif ratio >= 0.55:
        grade = "C+"
    else:
        grade = "C"

    readiness = buyer_readiness_bundle(
        gates=gates,
        critical_pass=critical_pass,
        evidence_pass=evidence_pass,
        vertical="racing",
    )

    return {
        "base_url": base_url,
        "revision": (ping_json or {}).get("revision"),
        "probes": probes,
        "gates": gates,
        "critical_pass": critical_pass,
        "evidence_pass": evidence_pass,
        "evidence_grade": grade,
        "next_actions": _next_actions(gates),
        **readiness,
    }


def racing_evidence_gates() -> Dict[str, Any]:
    """
    Pass/fail gates for racing institutional parity (HTTP probe of hibs-racing).

    Engineering gates: link + cards + health reachable.
    Evidence gates: telemetry coverage, recon, paper sample (HTTP /api/health?full=1).
    """
    base = _racing_base_url()
    football = _football_base_url()
    probes: Dict[str, Any] = {"base_url": base, "probe_mode": "local" if base.startswith("http://127.") else "public"}

    ping_code, ping_body = _http_get(f"{base}/api/ping", timeout=_http_timeout_for(f"{base}/api/ping"))
    probes["ping"] = {"status": ping_code, "body_preview": ping_body[:200]}
    ping_ok = ping_code == 200
    ping_json = _parse_json(ping_body) if ping_ok else {}

    cards_code, cards_body = _http_get(f"{base}/cards", timeout=_http_timeout_for(f"{base}/cards"))
    probes["cards"] = {"status": cards_code, "bytes": len(cards_body)}
    cards_ok = cards_code in (200, 302)
    cards_nonempty = cards_ok and len(cards_body) > 800 and "card" in cards_body.lower()

    health_code, health_body = _http_get(
        f"{base}/api/health?full=1", timeout=_http_timeout_for(f"{base}/api/health")
    )
    probes["health"] = {"status": health_code}
    health_ok = health_code == 200
    health = _parse_json(health_body) if health_ok else {}

    port_code, _ = _http_get(f"{football}/api/racing/portfolio/summary")
    probes["portfolio_proxy"] = {"status": port_code}
    portfolio_ok = port_code in (200, 401)

    return racing_evidence_gates_from_health(
        health,
        probes=probes,
        base_url=base,
        ping_json=ping_json,
        health_ok=health_ok,
        ping_ok=ping_ok,
        cards_ok=cards_ok,
        cards_nonempty=cards_nonempty,
        cards_body_len=len(cards_body) if cards_ok else 0,
        portfolio_ok=portfolio_ok,
        port_code=port_code,
        ping_code=ping_code,
        cards_code=cards_code,
        health_code=health_code,
    )


def _next_actions(gates: List[Dict[str, Any]]) -> List[str]:
    by_id = {g["id"]: g for g in gates}
    actions: List[str] = []
    if not by_id.get("R1_ping", {}).get("pass"):
        actions.append("./scripts/link_racing_production.sh")
    if not by_id.get("R2_cards", {}).get("pass") or not by_id.get("R2b_cards_data", {}).get("pass"):
        actions.append("./scripts/install_racing_vps_cron.sh")
        actions.append("RACING_VPS_CRON_SMOKE=1 ./scripts/install_racing_vps_cron.sh")
    if not by_id.get("R3_health", {}).get("pass"):
        actions.append("hibs-racing: /api/health 200 — or use /api/inst-pp/racing/health aggregator")
    if not by_id.get("R5_coverage", {}).get("pass"):
        actions.append("telemetry_balance.coverage_pct — hibs-racing /api/health?full=1")
    if not by_id.get("R6_recon_clean", {}).get("pass"):
        actions.append("cd ~/hibs-racing && bash scripts/daily_refresh.sh")
    if not actions:
        actions.append("./scripts/export_racing_data_room.sh")
    return actions
