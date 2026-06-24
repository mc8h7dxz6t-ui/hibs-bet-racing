"""Record drift gate evaluations on the institutional ledger."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from drift_gate.gate import DriftGateRequest, DriftGateResponse
from inst_spine.contracts import stable_id
from inst_spine.ledger import AppendOnlyLedger


def _default_db() -> Path:
    return Path("data/drift_gate.sqlite")


def record_drift_evaluation(
    *,
    request: DriftGateRequest,
    response: DriftGateResponse,
    actor: str = "drift-gate",
    database: Path | None = None,
) -> dict[str, Any]:
    db = database or _default_db()
    ledger = AppendOnlyLedger(db, writer_id=actor)
    manifest_id = request.request_id or stable_id(
        request.model_id,
        request.version,
        response.decision.value,
        str(response.reports[0].feature if response.reports else "none"),
    )
    entry = ledger.append(
        event_type="drift_gate_evaluation",
        payload={
            "model_id": request.model_id,
            "model_version": request.version,
            "feature_vector": request.feature_vector,
            "decision": response.decision.value,
            "reason": response.reason,
            "mode": response.mode.value,
            "shadow_would_reject": response.shadow_would_reject,
            "reports": response.to_dict()["reports"],
        },
        manifest_id=manifest_id,
        metadata={
            "model_id": request.model_id,
            "model_version": request.version,
            "governance_action": "drift_gate",
        },
    )
    return entry.to_dict()
