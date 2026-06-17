"""Compliance P2 — deterministic audit bundle export with cryptographic sealing."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inst_spine.check import run_institutional_check
from inst_spine.hash import (
    GENESIS_EVENT,
    read_genesis_anchor,
    verify_chain,
    verify_genesis_block,
    verify_lamport_monotonic,
)
from inst_spine.ledger import AppendOnlyLedger


@dataclass(frozen=True)
class ExportValidation:
    ok: bool
    genesis_ok: bool
    chain_ok: bool
    lamport_ok: bool
    message: str
    details: dict[str, Any]


@dataclass(frozen=True)
class AuditBundleResult:
    ok: bool
    out_dir: Path
    tarball_path: Path | None
    bundle_sha256: str
    validation: ExportValidation
    institutional_passed: bool


def _canonical_json_bytes(payload: Any) -> bytes:
    return json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode("utf-8")


def validate_before_export(
    *,
    ledger: AppendOnlyLedger,
    anchor_path: Path | None = None,
) -> ExportValidation:
    """
    P2 pre-export gates — abort bundle if any check fails.
    1. Genesis anchor matches WAL Block 0
    2. Hash chain continuity (verify_chain)
    3. Lamport strict monotonicity per writer
    """
    entries = ledger.list_entries()
    anchor = read_genesis_anchor(anchor_path or ledger.anchor_path)
    genesis_row = entries[0] if entries else None

    genesis = verify_genesis_block(genesis_row, anchor=anchor)
    chain = verify_chain(entries, anchor=anchor, require_genesis=True)
    lamport_ok = verify_lamport_monotonic(entries)

    ok = genesis.ok and chain.ok and lamport_ok
    if not genesis.ok:
        msg = genesis.message
    elif not chain.ok:
        msg = chain.message
    elif not lamport_ok:
        msg = "lamport sequence violation — possible backdating or splice"
    else:
        msg = "export validation passed"

    return ExportValidation(
        ok=ok,
        genesis_ok=genesis.ok,
        chain_ok=chain.ok,
        lamport_ok=lamport_ok,
        message=msg,
        details={
            "entries": len(entries),
            "genesis_message": genesis.message,
            "chain_message": chain.message,
            "instance_uuid": ledger._instance_uuid,
        },
    )


def _write_bundle_files(
    *,
    out_dir: Path,
    ledger: AppendOnlyLedger,
    validation: ExportValidation,
    report_dict: dict[str, Any],
    verify_dict: dict[str, Any],
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = ledger.list_entries()
    wal_all = ledger.wal.read_all()

    files: dict[str, bytes] = {
        "MANIFEST.json": _canonical_json_bytes(
            {
                "protocol": "inst-spine-audit-bundle-v1",
                "instance_uuid": ledger._instance_uuid,
                "entry_count": len(entries),
                "wal_record_count": len(wal_all),
                "validation": {
                    "genesis_ok": validation.genesis_ok,
                    "chain_ok": validation.chain_ok,
                    "lamport_ok": validation.lamport_ok,
                    "message": validation.message,
                },
            }
        ),
        "ledger_entries.json": _canonical_json_bytes(entries),
        "verify.json": _canonical_json_bytes(verify_dict),
        "institutional_check.json": _canonical_json_bytes(report_dict),
        "genesis_anchor.json": _canonical_json_bytes(read_genesis_anchor(ledger.anchor_path) or {}),
        "wal_full.json": _canonical_json_bytes(wal_all),
    }

    for name, content in sorted(files.items()):
        (out_dir / name).write_bytes(content)

    readme = (
        "Inst++ audit bundle (P2 deterministic export)\n"
        f"entries: {len(entries)}\n"
        f"genesis_ok: {validation.genesis_ok}\n"
        f"chain_ok: {validation.chain_ok}\n"
        f"lamport_ok: {validation.lamport_ok}\n"
        f"institutional_check: {report_dict.get('passed')}\n"
    )
    (out_dir / "README.txt").write_text(readme, encoding="utf-8")


def deterministic_tarball(source_dir: Path) -> bytes:
    """
    Byte-stable tar — fixed uid/gid/mtime, sorted paths.
    Identical ledger state → identical tarball bytes (F9 reproducibility).
    """
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file():
                continue
            arcname = str(path.relative_to(source_dir)).replace("\\", "/")
            data = path.read_bytes()
            info = tarfile.TarInfo(name=arcname)
            info.size = len(data)
            info.mtime = 0
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o644
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_audit_bundle(
    database: Path,
    *,
    out_dir: Path | None = None,
    tarball_path: Path | None = None,
    abort_on_fail: bool = True,
) -> AuditBundleResult:
    """
    Full P2 pipeline:
      validate → write canonical JSON files → deterministic tar → SHA256 sidecar
    """
    db = Path(database)
    out = out_dir or db.parent / "audit_bundle"
    tar_path = tarball_path or db.parent / "audit_bundle.tar"

    ledger = AppendOnlyLedger(db)
    validation = validate_before_export(ledger=ledger)
    verify_dict = ledger.verify()
    report = run_institutional_check(ledger=ledger)

    if abort_on_fail and not validation.ok:
        return AuditBundleResult(
            ok=False,
            out_dir=out,
            tarball_path=None,
            bundle_sha256="",
            validation=validation,
            institutional_passed=report.passed,
        )

    _write_bundle_files(
        out_dir=out,
        ledger=ledger,
        validation=validation,
        report_dict=report.to_dict(),
        verify_dict=verify_dict,
    )

    tar_bytes = deterministic_tarball(out)
    tar_path.write_bytes(tar_bytes)
    digest = sha256_bytes(tar_bytes)
    sidecar = {
        "algorithm": "sha256",
        "bundle_file": tar_path.name,
        "bundle_sha256": digest,
        "entry_count": len(ledger.list_entries()),
        "instance_uuid": ledger._instance_uuid,
        "protocol": "inst-spine-audit-bundle-v1",
    }
    (tar_path.with_suffix(tar_path.suffix + ".sha256.json")).write_text(
        json.dumps(sidecar, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (tar_path.with_suffix(tar_path.suffix + ".sha256")).write_text(f"{digest}  {tar_path.name}\n", encoding="utf-8")

    return AuditBundleResult(
        ok=validation.ok,
        out_dir=out,
        tarball_path=tar_path,
        bundle_sha256=digest,
        validation=validation,
        institutional_passed=report.passed,
    )


def verify_bundle_reproducible(database: Path, *, runs: int = 2) -> tuple[bool, str]:
    """F9 gate — identical state produces identical tarball hash."""
    db = Path(database)
    digests: list[str] = []
    for i in range(runs):
        out = db.parent / f"_repro_{i}"
        tar = db.parent / f"_repro_{i}.tar"
        result = build_audit_bundle(db, out_dir=out, tarball_path=tar)
        if not result.ok:
            return False, f"export failed on run {i}: {result.validation.message}"
        digests.append(result.bundle_sha256)
    if len(set(digests)) != 1:
        return False, f"non-deterministic export: {digests}"
    return True, digests[0]
