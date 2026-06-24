"""F8 retention — epoch Merkle compaction without silent deletion."""

from __future__ import annotations

import hashlib
from typing import Any


def merkle_root(leaf_hashes: list[str]) -> str:
    """Binary Merkle root over sorted leaf SHA256 hex digests."""
    if not leaf_hashes:
        return hashlib.sha256(b"empty-epoch").hexdigest()
    layer = sorted(leaf_hashes)
    while len(layer) > 1:
        nxt: list[str] = []
        for i in range(0, len(layer), 2):
            left = layer[i]
            right = layer[i + 1] if i + 1 < len(layer) else left
            nxt.append(hashlib.sha256(f"{left}:{right}".encode()).hexdigest())
        layer = nxt
    return layer[0]


def epoch_compaction_events(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in entries if e.get("event_type") == "epoch_compaction"]


def evaluate_retention_policy(
    entries: list[dict[str, Any]],
    *,
    max_entries_before_compaction: int = 50_000,
) -> tuple[bool, str]:
    """
    F8 honesty gate:
    - Ledgers within size budget pass without compaction.
    - Larger ledgers require at least one epoch_compaction event sealing prior entry hashes.
    """
    if not entries:
        return True, "empty ledger"
    epochs = epoch_compaction_events(entries)
    count = len(entries)
    if count <= max_entries_before_compaction:
        return True, f"within retention budget ({count} entries)"
    if epochs:
        roots = [
            str((e.get("payload") or {}).get("merkle_root") or "")
            for e in epochs
        ]
        roots = [r for r in roots if r]
        if roots:
            return True, f"epoch compaction sealed ({len(roots)} root(s), {count} entries)"
    return (
        False,
        f"retention required: {count} entries exceed budget {max_entries_before_compaction} "
        "without epoch_compaction",
    )


def build_epoch_compaction_payload(
    entries: list[dict[str, Any]],
    *,
    epoch_id: str,
    through_entry_id: str,
) -> dict[str, Any]:
    """Build payload for epoch_compaction ledger event."""
    leaf_hashes = [
        str(e.get("chain_hash") or e.get("entry_id") or "")
        for e in entries
        if e.get("entry_id") and e.get("entry_id") <= through_entry_id
    ]
    leaf_hashes = [h for h in leaf_hashes if h]
    root = merkle_root(leaf_hashes)
    return {
        "epoch_id": epoch_id,
        "through_entry_id": through_entry_id,
        "entry_count": len(leaf_hashes),
        "merkle_root": root,
    }
