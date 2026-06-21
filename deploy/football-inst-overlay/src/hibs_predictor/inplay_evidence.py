"""In-play institutional evidence gates — probes FVE /api/inplay/evidence (football-app)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

from hibs_predictor.evidence_presentation import buyer_readiness_bundle, gate_row
from hibs_predictor.fve_status import fve_api_base_url, fve_integration_enabled


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except ValueError:
        return default


def _http_timeout() -> float:
    return _env_float("HIBS_INPLAY_EVIDENCE_TIMEOUT", 12.0)


def _http_get(url: str, *, timeout: float | None = None) -> Tuple[int, str]:
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "hibs-bet-inplay-evidence/1.0", "Accept": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout or _http_timeout()) as resp:
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


def _unreachable_gates(*, base_url: str, probes: Dict[str, Any], reason: str) -> Dict[str, Any]:
    gates: List[Dict[str, Any]] = [
        gate_row(
            "I0_fve",
            label="FVE in-play evidence API",
            passed=False,
            actual=probes.get("evidence", {}).get("status"),
            threshold="200",
            message=reason,
            critical=True,
        ),
    ]
    critical_pass = False
    evidence_pass = False
    readiness = buyer_readiness_bundle(
        gates=gates,
        critical_pass=critical_pass,
        evidence_pass=evidence_pass,
        vertical="inplay",
    )
    return {
        "base_url": base_url,
        "integration_enabled": fve_integration_enabled(),
        "probes": probes,
        "gates": gates,
        "critical_pass": critical_pass,
        "evidence_pass": evidence_pass,
        "evidence_grade": "D",
        "next_actions": [reason],
        **readiness,
    }


def inplay_evidence_gates_from_payload(
    payload: Dict[str, Any],
    *,
    base_url: str,
    probes: Dict[str, Any],
    evidence_ok: bool = True,
) -> Dict[str, Any]:
    """Normalize FVE inplay evidence payload for hibs-bet health + verify scripts."""
    if not evidence_ok or not payload:
        return _unreachable_gates(
            base_url=base_url,
            probes=probes,
            reason="FVE /api/inplay/evidence unreachable — deploy football-app inplay package",
        )

    gates = payload.get("gates")
    if not isinstance(gates, list) or not gates:
        return _unreachable_gates(
            base_url=base_url,
            probes=probes,
            reason="FVE inplay evidence empty — check HIBS_INPLAY_EVIDENCE_DB on FVE host",
        )

    readiness = buyer_readiness_bundle(
        gates=gates,
        critical_pass=bool(payload.get("critical_pass")),
        evidence_pass=bool(payload.get("evidence_pass")),
        vertical="inplay",
    )
    return {
        "base_url": base_url,
        "integration_enabled": fve_integration_enabled(),
        "since_deploy_iso": payload.get("since_deploy_iso"),
        "probes": probes,
        "gates": gates,
        "critical_pass": payload.get("critical_pass"),
        "evidence_pass": payload.get("evidence_pass"),
        "evidence_grade": payload.get("evidence_grade"),
        "telemetry": payload.get("telemetry"),
        "next_actions": _next_actions(gates),
        **readiness,
    }


def inplay_evidence_gates() -> Dict[str, Any]:
    """
    Pass/fail gates for in-play institutional evidence (HTTP probe of FVE).

    Engineering gate: FVE /api/inplay/evidence reachable.
    Evidence gates I1–I5: computed on FVE from SQLite telemetry store.
    """
    base = fve_api_base_url()
    probes: Dict[str, Any] = {"base_url": base, "probe_mode": "fve"}

    health_code, health_body = _http_get(f"{base}/health")
    probes["health"] = {"status": health_code}
    health = _parse_json(health_body) if health_code == 200 else {}

    evidence_code, evidence_body = _http_get(f"{base}/api/inplay/evidence")
    probes["evidence"] = {"status": evidence_code, "body_preview": evidence_body[:240]}
    evidence_ok = evidence_code == 200
    payload = _parse_json(evidence_body) if evidence_ok else {}

    if not evidence_ok and health_code == 200:
        summary = health.get("inplay_evidence") if isinstance(health.get("inplay_evidence"), dict) else {}
        if summary:
            probes["evidence"]["health_summary"] = summary

    return inplay_evidence_gates_from_payload(
        payload,
        base_url=base,
        probes=probes,
        evidence_ok=evidence_ok,
    )


def _next_actions(gates: List[Dict[str, Any]]) -> List[str]:
    actions: List[str] = []
    for gate in gates:
        if gate.get("pass"):
            continue
        msg = (gate.get("message") or "").strip()
        label = gate.get("label") or gate.get("id")
        if msg:
            actions.append(f"{label}: {msg}")
        else:
            actions.append(f"{label}: need {gate.get('threshold')}")
    return actions[:8]
