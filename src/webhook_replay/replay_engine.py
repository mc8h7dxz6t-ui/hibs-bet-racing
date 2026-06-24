"""Deterministic replay engine with diff reporting."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from inst_spine.ledger import AppendOnlyLedger
from webhook_replay.capture import CaptureManifest, CaptureStore


@dataclass
class ReplayDiff:
    field: str
    expected: Any
    actual: Any

    def to_dict(self) -> dict[str, Any]:
        return {"field": self.field, "expected": self.expected, "actual": self.actual}


@dataclass
class ReplayResult:
    ok: bool
    capture_id: str
    message: str
    diffs: list[ReplayDiff] = field(default_factory=list)
    idempotent_match: bool = True
    body_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "capture_id": self.capture_id,
            "message": self.message,
            "idempotent_match": self.idempotent_match,
            "body_sha256": self.body_sha256,
            "diffs": [d.to_dict() for d in self.diffs],
        }


HandlerFn = Callable[[CaptureManifest, bytes], dict[str, Any]]


def _default_handler(manifest: CaptureManifest, body: bytes) -> dict[str, Any]:
    """Reference handler — structural integrity + JSON parse check."""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        return {"status": "reject", "reason": f"json_decode:{exc.msg}"}
    return {
        "status": "accept",
        "capture_id": manifest.capture_id,
        "payload_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
    }


class ReplayEngine:
    """Replay captured webhooks in air-gapped mode — no network."""

    def __init__(
        self,
        store: CaptureStore,
        *,
        handler: HandlerFn | None = None,
        ledger: AppendOnlyLedger | None = None,
    ) -> None:
        self.store = store
        self.handler = handler or _default_handler
        self.ledger = ledger

    def replay_file(self, path: Path, *, expected_sha256: str | None = None) -> ReplayResult:
        manifest, body = self.store.read(path)
        return self.replay_capture(manifest, body, expected_sha256=expected_sha256)

    def replay_capture(
        self,
        manifest: CaptureManifest,
        body: bytes,
        *,
        expected_sha256: str | None = None,
    ) -> ReplayResult:
        body_hash = hashlib.sha256(body).hexdigest()
        diffs: list[ReplayDiff] = []
        stored_hash = manifest.extras.get("payload_sha256") or manifest.payload_sha256
        if stored_hash and stored_hash != body_hash:
            diffs.append(ReplayDiff("payload_sha256", stored_hash, body_hash))

        if expected_sha256 and expected_sha256 != body_hash:
            diffs.append(ReplayDiff("expected_sha256", expected_sha256, body_hash))

        handler_result = self.handler(manifest, body)
        idempotent_match = not diffs and handler_result.get("status") != "reject"
        ok = idempotent_match

        if self.ledger is not None:
            self.ledger.append(
                event_type="webhook_replay",
                payload={
                    "capture_id": manifest.capture_id,
                    "tenant_id": manifest.tenant_id,
                    "provider": manifest.provider,
                    "body_sha256": body_hash,
                    "replay_ok": ok,
                    "handler_result": handler_result,
                    "diffs": [d.to_dict() for d in diffs],
                },
                manifest_id=manifest.capture_id,
                metadata={"replay_engine": "webhook-replay"},
            )

        return ReplayResult(
            ok=ok,
            capture_id=manifest.capture_id,
            message="replay_ok" if ok else "replay_mismatch",
            diffs=diffs,
            idempotent_match=idempotent_match,
            body_sha256=body_hash,
        )

    def replay_all(self) -> list[ReplayResult]:
        return [self.replay_file(p) for p in self.store.list_captures()]
