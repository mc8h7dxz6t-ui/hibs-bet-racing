"""Sequential hash chain — H_n = SHA256(M_n || H_{n-1} || lamport_n)."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from inst_spine.contracts import canonical_json

GENESIS_HASH = "0" * 64


def chain_hash(
    *,
    payload: dict[str, Any],
    prev_hash: str,
    lamport_seq: int,
    metadata: dict[str, Any] | None = None,
) -> str:
    """Compute H_n for a ledger entry."""
    manifest = {
        "payload": payload,
        "metadata": metadata or {},
        "lamport_seq": lamport_seq,
    }
    material = f"{canonical_json(manifest)}|{prev_hash}|{lamport_seq}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ChainVerifyResult:
    ok: bool
    entries_checked: int
    first_mismatch_index: int | None
    message: str


def verify_chain(entries: list[dict[str, Any]]) -> ChainVerifyResult:
    """
    Walk ledger rows in order. Each row must have:
      payload, lamport_seq, prev_hash, entry_hash
    """
    if not entries:
        return ChainVerifyResult(ok=True, entries_checked=0, first_mismatch_index=None, message="empty chain")

    prev = GENESIS_HASH
    for idx, row in enumerate(entries):
        stored_prev = str(row.get("prev_hash") or "")
        if stored_prev != prev:
            return ChainVerifyResult(
                ok=False,
                entries_checked=idx,
                first_mismatch_index=idx,
                message=f"prev_hash mismatch at index {idx}",
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
            )
        prev = stored

    return ChainVerifyResult(
        ok=True,
        entries_checked=len(entries),
        first_mismatch_index=None,
        message=f"chain verified ({len(entries)} entries)",
    )


def verify_lamport_monotonic(entries: list[dict[str, Any]], *, writer_id: str | None = None) -> bool:
    """F4: lamport_seq strictly increasing per writer."""
    last: dict[str, int] = {}
    for row in entries:
        w = str(row.get("writer_id") or "")
        if writer_id and w != writer_id:
            continue
        seq = int(row["lamport_seq"])
        if seq <= last.get(w, 0):
            return False
        last[w] = seq
    return True
