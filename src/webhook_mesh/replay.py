"""Dead-letter replay guards — block poison payload re-ingestion loops."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

POISON_STATUS_CODES = frozenset({400, 422})


def assess_payload_integrity(payload: bytes) -> tuple[bool, str | None]:
    if not payload:
        return False, "empty_payload"
    try:
        json.loads(payload)
    except json.JSONDecodeError as exc:
        return False, f"json_decode:{exc.msg}"
    except UnicodeDecodeError:
        return False, "utf8_decode_failed"
    return True, None


def build_dead_letter_meta(
    *,
    manifest_id: str,
    payload: bytes,
    target_url: str,
    payload_id: str = "",
    last_status_code: int | None = None,
    failure_reason: str = "max_retries_exceeded",
    attempts: int = 0,
) -> dict[str, Any]:
    import hashlib

    ok, structural_reason = assess_payload_integrity(payload)
    replay_blocked = not ok or last_status_code in POISON_STATUS_CODES
    block_reason: str | None = None
    if not ok:
        block_reason = structural_reason
    elif last_status_code in POISON_STATUS_CODES:
        block_reason = f"downstream_rejected:{last_status_code}"

    return {
        "manifest_id": manifest_id,
        "payload_id": payload_id or manifest_id,
        "target_url": target_url,
        "last_status_code": last_status_code,
        "failure_reason": failure_reason,
        "attempts": attempts,
        "replay_blocked": replay_blocked,
        "block_reason": block_reason,
        "schema_version_required": None,
        "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "structurally_valid": ok,
    }


def dead_letter_meta_path(
    base: Path,
    *,
    manifest_id: str,
    payload_id: str = "",
    last_status_code: int | None = None,
) -> Path:
    label = payload_id or manifest_id
    status = last_status_code if last_status_code is not None else "unknown"
    return base / f"{label}.err_{status}.json"


def load_dead_letter_meta(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def can_replay_dead_letter(meta: dict[str, Any]) -> tuple[bool, str]:
    if not meta.get("replay_blocked"):
        return True, "ok"
    if meta.get("schema_version_required"):
        return True, "schema_version_cleared"
    return False, str(meta.get("block_reason") or "replay_blocked")


def find_dead_letter_record(
    dead_letter_dir: str | Path,
    *,
    manifest_id: str | None = None,
    payload_id: str | None = None,
) -> tuple[Path, Path, dict[str, Any]] | None:
    base = Path(dead_letter_dir)
    if not base.exists():
        return None
    if manifest_id:
        bin_path = base / f"{manifest_id}.bin"
        if not bin_path.exists():
            return None
        for meta_path in sorted(base.glob("*.err_*.json")):
            meta = load_dead_letter_meta(meta_path)
            if meta.get("manifest_id") == manifest_id:
                return bin_path, meta_path, meta
        return None
    if payload_id:
        for meta_path in sorted(base.glob(f"{payload_id}.err_*.json")):
            meta = load_dead_letter_meta(meta_path)
            mid = str(meta.get("manifest_id", payload_id))
            bin_path = base / f"{mid}.bin"
            if bin_path.exists():
                return bin_path, meta_path, meta
    return None
