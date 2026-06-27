"""F8 retention drill — epoch compaction + export (Wave 2)."""

from __future__ import annotations

from pathlib import Path

from inst_spine.export import build_audit_bundle, verify_audit_bundle
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.retention import build_epoch_compaction_payload, evaluate_retention_policy


def test_f8_retention_drill_compaction_and_export(tmp_path: Path):
    db = tmp_path / "retention.sqlite"
    ledger = AppendOnlyLedger(db)
    for i in range(12):
        ledger.append(
            event_type="decision",
            payload={"i": i},
            manifest_id=f"m-{i}",
        )
    entries = ledger.list_entries()
    last_id = entries[-1]["entry_id"]
    payload = build_epoch_compaction_payload(entries, epoch_id="e1", through_entry_id=last_id)
    ledger.append(event_type="epoch_compaction", payload=payload, manifest_id="epoch-e1")

    ok, msg = evaluate_retention_policy(
        ledger.list_entries(),
        max_entries_before_compaction=5,
    )
    assert ok is True, msg

    tar = tmp_path / "retention_bundle.tar"
    result = build_audit_bundle(db, tarball_path=tar, product="retention-drill")
    assert result.ok is True
    verify = verify_audit_bundle(tar)
    assert verify.ok is True

    import json
    import tarfile

    with tarfile.open(tar, "r") as tf:
        epoch = json.loads(tf.extractfile("epoch_roots.json").read().decode())
    assert epoch["entry_count"] >= 12
    assert len(epoch["merkle_root"]) == 64
