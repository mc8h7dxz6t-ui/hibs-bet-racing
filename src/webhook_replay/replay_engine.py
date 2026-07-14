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
        mesh_ledger_db: Path | None = None,
    ) -> None:
        self.store = store
        self.handler = handler or _default_handler
        self.ledger = ledger
        self.mesh_ledger_db = mesh_ledger_db

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
        lamport_ok, lamport_detail = self._verify_ingress_lamport(manifest)
        ok = idempotent_match and lamport_ok
        if not lamport_ok:
            diffs.append(ReplayDiff("lamport_anchor", "ingress<=capture", lamport_detail))

        if self.ledger is not None:
            self.ledger.append(
                event_type="webhook_replay",
                payload={
                    "capture_id": manifest.capture_id,
                    "tenant_id": manifest.tenant_id,
                    "provider": manifest.provider,
                    "body_sha256": body_hash,
                    "replay_ok": ok,
                    "lamport_ok": lamport_ok,
                    "lamport_detail": lamport_detail,
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

    def replay_batch_parallel(
        self,
        paths: list[Path] | None = None,
        *,
        max_workers: int | None = None,
    ) -> list[ReplayResult]:
        """Bounded parallel replay for large capture sets (scale layer D)."""
        from concurrent.futures import ThreadPoolExecutor
        import os

        targets = list(paths or self.store.list_captures())
        workers = max_workers if max_workers is not None else int(os.getenv("WEBHOOK_REPLAY_WORKERS", "4"))
        workers = max(1, min(workers, 32))
        if not targets:
            return []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            return list(pool.map(self.replay_file, targets))

    def _verify_ingress_lamport(self, manifest: CaptureManifest) -> tuple[bool, str]:
        if self.mesh_ledger_db is None or not self.mesh_ledger_db.is_file():
            return True, "mesh_ledger_not_configured"
        cap_lamport = int(manifest.lamport_seq or manifest.extras.get("lamport") or 0)
        if cap_lamport <= 0:
            return True, "capture_lamport_missing"
        ledger = AppendOnlyLedger(self.mesh_ledger_db)
        ingress_lamports: list[int] = []
        for row in ledger.list_entries():
            if row.get("event_type") not in ("webhook_ingress", "webhook_delivery"):
                continue
            payload = row.get("payload") or {}
            if str(payload.get("manifest_id")) != manifest.capture_id:
                continue
            ingress_lamports.append(int(payload.get("lamport") or row.get("lamport_seq") or 0))
        if not ingress_lamports:
            return True, "ingress_not_found"
        ingress_max = max(ingress_lamports)
        if cap_lamport > ingress_max:
            return False, f"capture_lamport={cap_lamport} > ingress_max={ingress_max}"
        return True, f"capture_lamport={cap_lamport} ingress_max={ingress_max}"
