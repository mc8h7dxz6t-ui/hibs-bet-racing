"""Sequential hash chain + Genesis Block protocol."""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inst_spine.contracts import canonical_json, stable_id

# H_{-1} — prev_hash for Block 0 (genesis) only. Not a valid chain endpoint.
GENESIS_PREV_HASH = "0" * 64
GENESIS_EVENT = "genesis"
GENESIS_LAMPORT = 0
GENESIS_PROTOCOL = "inst-spine-genesis-v1"

# Back-compat alias
GENESIS_HASH = GENESIS_PREV_HASH


def chain_hash(
    *,
    payload: dict[str, Any],
    prev_hash: str,
    lamport_seq: int,
    metadata: dict[str, Any] | None = None,
) -> str:
    """H_n = SHA256(M_n || H_{n-1} || lamport_n)."""
    manifest = {
        "payload": payload,
        "metadata": metadata or {},
        "lamport_seq": lamport_seq,
    }
    material = f"{canonical_json(manifest)}|{prev_hash}|{lamport_seq}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_genesis_record(
    *,
    instance_uuid: str,
    config_hash: str,
    writer_id: str,
    wall_time_utc: str,
) -> dict[str, Any]:
    """Block 0 — immutable installation origin. prev_hash = GENESIS_PREV_HASH."""
    payload = {
        "block": GENESIS_EVENT,
        "instance_uuid": instance_uuid,
        "config_hash": config_hash,
        "installation_lamport_zero": GENESIS_LAMPORT,
        "protocol": GENESIS_PROTOCOL,
    }
    metadata = {
        "signed": True,
        "protocol": GENESIS_PROTOCOL,
        "writer_id": writer_id,
    }
    entry_hash = chain_hash(
        payload=payload,
        prev_hash=GENESIS_PREV_HASH,
        lamport_seq=GENESIS_LAMPORT,
        metadata=metadata,
    )
    entry_id = stable_id(GENESIS_EVENT, instance_uuid, config_hash)
    return {
        "entry_id": entry_id,
        "event_type": GENESIS_EVENT,
        "writer_id": writer_id,
        "lamport_seq": GENESIS_LAMPORT,
        "wall_time_utc": wall_time_utc,
        "manifest_id": None,
        "payload": payload,
        "metadata": metadata,
        "prev_hash": GENESIS_PREV_HASH,
        "entry_hash": entry_hash,
        "is_genesis": True,
    }


def new_instance_uuid() -> str:
    return str(uuid.uuid4())


def write_genesis_anchor(path: Path, *, instance_uuid: str, genesis_hash: str, config_hash: str) -> None:
    """Sidecar anchor — detects wiped/replaced ledger without matching install."""
    anchor = {
        "instance_uuid": instance_uuid,
        "genesis_hash": genesis_hash,
        "config_hash": config_hash,
        "protocol": GENESIS_PROTOCOL,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(anchor, indent=2, sort_keys=True), encoding="utf-8")


def read_genesis_anchor(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True)
class ChainVerifyResult:
    ok: bool
    entries_checked: int
    first_mismatch_index: int | None
    message: str
    genesis_ok: bool = False


@dataclass(frozen=True)
class GenesisVerifyResult:
    ok: bool
    message: str


def verify_genesis_block(
    genesis_row: dict[str, Any] | None,
    *,
    anchor: dict[str, Any] | None = None,
) -> GenesisVerifyResult:
    if genesis_row is None:
        return GenesisVerifyResult(ok=False, message="genesis block missing")
    if genesis_row.get("event_type") != GENESIS_EVENT:
        return GenesisVerifyResult(ok=False, message="block 0 is not genesis event")
    if int(genesis_row.get("lamport_seq", -1)) != GENESIS_LAMPORT:
        return GenesisVerifyResult(ok=False, message="genesis lamport must be 0")
    if str(genesis_row.get("prev_hash") or "") != GENESIS_PREV_HASH:
        return GenesisVerifyResult(ok=False, message="genesis prev_hash invalid")

    payload = genesis_row.get("payload") or {}
    metadata = genesis_row.get("metadata") or {}
    expected = chain_hash(
        payload=payload,
        prev_hash=GENESIS_PREV_HASH,
        lamport_seq=GENESIS_LAMPORT,
        metadata=metadata,
    )
    stored = str(genesis_row.get("entry_hash") or "")
    if stored != expected:
        return GenesisVerifyResult(ok=False, message="genesis entry_hash tampered")

    if anchor is not None:
        if anchor.get("genesis_hash") != stored:
            return GenesisVerifyResult(ok=False, message="genesis anchor hash mismatch")
        inst = payload.get("instance_uuid")
        if anchor.get("instance_uuid") != inst:
            return GenesisVerifyResult(ok=False, message="genesis anchor instance_uuid mismatch")

    return GenesisVerifyResult(ok=True, message="genesis block valid")


def verify_chain(
    entries: list[dict[str, Any]],
    *,
    anchor: dict[str, Any] | None = None,
    require_genesis: bool = True,
) -> ChainVerifyResult:
    """
    Walk ledger rows. Block 0 must be signed genesis when require_genesis=True.
  Empty chain fails — cannot rebuild from null H_0 after DB wipe attack.
    """
    if not entries:
        return ChainVerifyResult(
            ok=False,
            entries_checked=0,
            first_mismatch_index=None,
            message="empty chain — genesis block required",
            genesis_ok=False,
        )

    genesis_row = entries[0]
    genesis_result = verify_genesis_block(genesis_row if require_genesis else None, anchor=anchor)
    if require_genesis and not genesis_result.ok:
        return ChainVerifyResult(
            ok=False,
            entries_checked=0,
            first_mismatch_index=0,
            message=genesis_result.message,
            genesis_ok=False,
        )

    prev = str(genesis_row.get("entry_hash") or GENESIS_PREV_HASH)
    start_idx = 1 if require_genesis else 0
    if not require_genesis:
        prev = GENESIS_PREV_HASH

    for idx in range(start_idx, len(entries)):
        row = entries[idx]
        stored_prev = str(row.get("prev_hash") or "")
        if stored_prev != prev:
            return ChainVerifyResult(
                ok=False,
                entries_checked=idx,
                first_mismatch_index=idx,
                message=f"prev_hash mismatch at index {idx}",
                genesis_ok=genesis_result.ok if require_genesis else False,
            )
        lamport = int(row["lamport_seq"])
        payload = row.get("payload") or {}
        metadata = row.get("metadata") or {}
        expected = chain_hash(
            payload=payload,
            prev_hash=prev,
            lamport_seq=lamport,
            metadata=metadata,
        )
        stored = str(row.get("entry_hash") or "")
        if stored != expected:
            return ChainVerifyResult(
                ok=False,
                entries_checked=idx,
                first_mismatch_index=idx,
                message=f"entry_hash mismatch at index {idx}",
                genesis_ok=genesis_result.ok if require_genesis else False,
            )
        prev = stored

    return ChainVerifyResult(
        ok=True,
        entries_checked=len(entries),
        first_mismatch_index=None,
        message=f"chain verified ({len(entries)} entries incl. genesis)",
        genesis_ok=True,
    )


def verify_chain_linkage(
    entries: list[dict[str, Any]],
    *,
    anchor: dict[str, Any] | None = None,
    require_genesis: bool = True,
) -> ChainVerifyResult:
    """
    Observation-lane offline verify — trust stored entry_hash links without
    recomputing from redacted payloads (export-time PHI/secret scrub).
    """
    if not entries:
        return ChainVerifyResult(
            ok=False,
            entries_checked=0,
            first_mismatch_index=None,
            message="empty chain — genesis block required",
            genesis_ok=False,
        )

    genesis_row = entries[0]
    genesis_result = verify_genesis_block(genesis_row if require_genesis else None, anchor=anchor)
    if require_genesis and not genesis_result.ok:
        return ChainVerifyResult(
            ok=False,
            entries_checked=0,
            first_mismatch_index=0,
            message=genesis_result.message,
            genesis_ok=False,
        )

    prev = str(genesis_row.get("entry_hash") or GENESIS_PREV_HASH)
    start_idx = 1 if require_genesis else 0
    if not require_genesis:
        prev = GENESIS_PREV_HASH

    for idx in range(start_idx, len(entries)):
        row = entries[idx]
        stored_prev = str(row.get("prev_hash") or "")
        if stored_prev != prev:
            return ChainVerifyResult(
                ok=False,
                entries_checked=idx,
                first_mismatch_index=idx,
                message=f"prev_hash mismatch at index {idx}",
                genesis_ok=genesis_result.ok if require_genesis else False,
            )
        stored = str(row.get("entry_hash") or "")
        if not stored or stored == GENESIS_PREV_HASH:
            return ChainVerifyResult(
                ok=False,
                entries_checked=idx,
                first_mismatch_index=idx,
                message=f"missing entry_hash at index {idx}",
                genesis_ok=genesis_result.ok if require_genesis else False,
            )
        prev = stored

    return ChainVerifyResult(
        ok=True,
        entries_checked=len(entries),
        first_mismatch_index=None,
        message=f"chain linkage verified ({len(entries)} entries incl. genesis)",
        genesis_ok=True,
    )


def verify_lamport_monotonic(entries: list[dict[str, Any]], *, writer_id: str | None = None) -> bool:
    """F4: lamport_seq strictly increasing per writer (genesis seq 0 excluded from tick stream)."""
    last: dict[str, int] = {}
    for row in entries:
        if row.get("event_type") == GENESIS_EVENT:
            continue
        w = str(row.get("writer_id") or "")
        if writer_id and w != writer_id:
            continue
        seq = int(row["lamport_seq"])
        if seq <= last.get(w, 0):
            return False
        last[w] = seq
    return True
