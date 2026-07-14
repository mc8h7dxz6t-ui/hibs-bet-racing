"""F8 retention drill — per-SKU epoch compaction + export (Wave 2)."""

from __future__ import annotations

from pathlib import Path

import pytest

from inst_spine.export import build_audit_bundle, verify_audit_bundle
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.retention import build_epoch_compaction_payload, evaluate_retention_policy

SKU_PRODUCTS = [
    "compliance-log",
    "proxy-risk",
    "altdata",
    "ai-kit",
    "webhook-mesh",
    "ad-guard",
    "health-telemetry",
    "model-governor",
    "drift-gate",
    "webhook-replay",
    "spend-guard",
    "agent-ledger",
]


@pytest.mark.parametrize("product", SKU_PRODUCTS)
def test_f8_retention_drill_per_sku(tmp_path: Path, product: str):
    db = tmp_path / f"{product.replace('-', '_')}.sqlite"
    ledger = AppendOnlyLedger(db)
    for i in range(8):
        ledger.append(
            event_type="decision",
            payload={"product": product, "i": i},
            manifest_id=f"{product}-m-{i}",
            metadata={"product": product},
        )
    entries = ledger.list_entries()
    last_id = entries[-1]["entry_id"]
    payload = build_epoch_compaction_payload(entries, epoch_id=f"{product}-e1", through_entry_id=last_id)
    ledger.append(
        event_type="epoch_compaction",
        payload=payload,
        manifest_id=f"{product}-epoch-e1",
        metadata={"product": product},
    )

    ok, msg = evaluate_retention_policy(
        ledger.list_entries(),
        max_entries_before_compaction=5,
    )
    assert ok is True, msg

    tar = tmp_path / f"{product}_bundle.tar"
    result = build_audit_bundle(db, tarball_path=tar, product=product)
    assert result.ok is True
    verify = verify_audit_bundle(tar)
    assert verify.ok is True

    import json
    import tarfile

    with tarfile.open(tar, "r") as tf:
        epoch = json.loads(tf.extractfile("epoch_roots.json").read().decode())
    assert epoch["entry_count"] >= 8
    assert len(epoch["merkle_root"]) == 64
