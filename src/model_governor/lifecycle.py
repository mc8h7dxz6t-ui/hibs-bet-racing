"""Model governance lifecycle FSM — enforce register → approve → deploy ordering."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from inst_spine.errors import IngestValidationError
from inst_spine.ledger import AppendOnlyLedger

_PREREQUISITES: dict[str, tuple[str, ...]] = {
    "register": (),
    "approve": ("register",),
    "reject": ("register",),
    "deploy": ("approve",),
    "retire": ("deploy",),
    "drift_alert": ("register",),
}


def _actions_for_model(
    entries: list[dict[str, Any]],
    *,
    model_id: str,
    version: str,
) -> set[str]:
    seen: set[str] = set()
    for row in entries:
        if row.get("event_type") != "model_governance":
            continue
        payload = row.get("payload") or {}
        snap = payload.get("model_snapshot") or {}
        if str(snap.get("model_id")) != model_id or str(snap.get("version")) != version:
            continue
        act = str(payload.get("action") or "").lower()
        if act:
            seen.add(act)
    return seen


def validate_lifecycle_transition(
    *,
    action: str,
    model_id: str,
    version: str,
    database: Path,
) -> None:
    """Fail-closed if governance action violates lifecycle FSM."""
    act = (action or "").strip().lower()
    required = _PREREQUISITES.get(act)
    if required is None:
        return
    ledger = AppendOnlyLedger(database)
    seen = _actions_for_model(ledger.list_entries(), model_id=model_id, version=version)
    missing = [r for r in required if r not in seen]
    if missing:
        raise IngestValidationError(
            f"lifecycle FSM: {act!r} requires prior action(s) {missing} for "
            f"{model_id}@{version}; seen={sorted(seen)}"
        )


def validate_deploy_drift_gate(
    *,
    model_id: str,
    version: str,
    features: dict[str, float],
    baseline_path: Path,
    mode: str = "shadow",
    database: Path | None = None,
) -> dict[str, Any]:
    """
    Deploy gate — require drift shadow evaluation before deploy is recorded.
  Raises IngestValidationError on enforce-mode KILL/REJECT.
    """
    from drift_gate.gate import DriftGateDecision
    from drift_gate.integrate import evaluate_model_features

    result = evaluate_model_features(
        model_id=model_id,
        version=version,
        features=features,
        baseline_path=baseline_path,
        mode=mode,
        database=database,
    )
    resp = result.get("response") or {}
    decision = str(resp.get("decision") or "")
    if decision in (DriftGateDecision.KILL.value, DriftGateDecision.REJECT.value) and mode == "enforce":
        raise IngestValidationError(f"deploy blocked by drift gate: {resp.get('reason')}")
    return result
