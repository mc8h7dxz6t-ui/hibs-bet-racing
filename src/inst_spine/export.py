"""Compliance P2 — deterministic audit bundle export with cryptographic sealing."""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from inst_spine.check import build_compliance_context, run_institutional_check
from inst_spine.bundle_sign import write_signature_sidecar
from inst_spine.hash import (
    GENESIS_EVENT,
    read_genesis_anchor,
    verify_chain,
    verify_genesis_block,
    verify_lamport_monotonic,
)
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.retention import merkle_root


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


@dataclass(frozen=True)
class BundleVerifyResult:
    """Offline auditor replay — no live database required."""

    ok: bool
    genesis_ok: bool
    chain_ok: bool
    lamport_ok: bool
    bundle_sha256_ok: bool
    institutional_passed: bool
    message: str
    details: dict[str, Any]


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
    product: str | None = None,
    extra_files: dict[str, Path] | None = None,
) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    entries = ledger.list_entries()
    wal_all = ledger.wal.read_all()

    manifest: dict[str, Any] = {
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
    if product:
        manifest["product"] = product

    leaf_hashes = [
        str(e.get("entry_hash") or e.get("entry_id") or "")
        for e in entries
        if e.get("event_type") != GENESIS_EVENT and (e.get("entry_hash") or e.get("entry_id"))
    ]
    epoch_roots = {
        "protocol": "inst-spine-epoch-merkle-v1",
        "entry_count": len(leaf_hashes),
        "merkle_root": merkle_root(leaf_hashes),
    }

    files: dict[str, bytes] = {
        "MANIFEST.json": _canonical_json_bytes(manifest),
        "ledger_entries.json": _canonical_json_bytes(entries),
        "verify.json": _canonical_json_bytes(verify_dict),
        "institutional_check.json": _canonical_json_bytes(report_dict),
        "genesis_anchor.json": _canonical_json_bytes(read_genesis_anchor(ledger.anchor_path) or {}),
        "wal_full.json": _canonical_json_bytes(wal_all),
        "epoch_roots.json": _canonical_json_bytes(epoch_roots),
    }

    for name, content in sorted(files.items()):
        (out_dir / name).write_bytes(content)

    if extra_files:
        extras_dir = out_dir / "extras"
        extras_dir.mkdir(parents=True, exist_ok=True)
        manifest_extras: list[dict[str, str]] = []
        for arc_name, src in sorted(extra_files.items()):
            if not src.is_file():
                continue
            data = src.read_bytes()
            dest = extras_dir / arc_name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
            manifest_extras.append(
                {
                    "path": f"extras/{arc_name}",
                    "sha256": sha256_bytes(data),
                    "bytes": str(len(data)),
                }
            )
        (out_dir / "bundle_extras.json").write_bytes(_canonical_json_bytes(manifest_extras))

    readme = (
        "Inst++ audit bundle (P2 deterministic export)\n"
        f"product: {product or 'inst-spine'}\n"
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


def _read_tar_member(tar: tarfile.TarFile, name: str) -> dict[str, Any] | list[Any] | None:
    try:
        member = tar.getmember(name)
    except KeyError:
        return None
    raw = tar.extractfile(member)
    if raw is None:
        return None
    return json.loads(raw.read().decode("utf-8"))


def verify_audit_bundle(
    tarball_path: Path,
    *,
    anchor_path: Path | None = None,
    expected_sha256: str | None = None,
) -> BundleVerifyResult:
    """
    Offline auditor dry-run — extract tarball, replay chain + F1–F9 without live DB.
    Optional offsite genesis anchor overrides bundle-local anchor file.
    """
    tar_path = Path(tarball_path)
    tar_bytes = tar_path.read_bytes()
    digest = sha256_bytes(tar_bytes)
    sha_ok = True
    if expected_sha256 is not None:
        sha_ok = digest == expected_sha256
    else:
        sidecar = tar_path.with_suffix(tar_path.suffix + ".sha256.json")
        if sidecar.is_file():
            try:
                sidecar_data = json.loads(sidecar.read_text(encoding="utf-8"))
                expected = str(sidecar_data.get("bundle_sha256") or "")
                if expected:
                    sha_ok = digest == expected
            except json.JSONDecodeError:
                sha_ok = False

    with tarfile.open(fileobj=io.BytesIO(tar_bytes), mode="r") as tar:
        entries = _read_tar_member(tar, "ledger_entries.json")
        anchor_bundle = _read_tar_member(tar, "genesis_anchor.json")
        report = _read_tar_member(tar, "institutional_check.json")
        manifest = _read_tar_member(tar, "MANIFEST.json")

    if not isinstance(entries, list):
        return BundleVerifyResult(
            ok=False,
            genesis_ok=False,
            chain_ok=False,
            lamport_ok=False,
            bundle_sha256_ok=sha_ok,
            institutional_passed=False,
            message="bundle missing ledger_entries.json",
            details={"bundle_sha256": digest},
        )

    anchor: dict[str, Any] | None = None
    if anchor_path is not None and Path(anchor_path).is_file():
        anchor = json.loads(Path(anchor_path).read_text(encoding="utf-8"))
    elif isinstance(anchor_bundle, dict) and anchor_bundle:
        anchor = anchor_bundle

    genesis_row = entries[0] if entries else None
    genesis = verify_genesis_block(genesis_row, anchor=anchor)
    chain = verify_chain(entries, anchor=anchor, require_genesis=True)
    lamport_ok = verify_lamport_monotonic(entries)
    inst_passed = bool((report or {}).get("passed")) if isinstance(report, dict) else False

    ok = genesis.ok and chain.ok and lamport_ok and sha_ok and inst_passed
    if not sha_ok:
        msg = "bundle SHA256 mismatch"
    elif not genesis.ok:
        msg = genesis.message
    elif not chain.ok:
        msg = chain.message
    elif not lamport_ok:
        msg = "lamport sequence violation"
    elif not inst_passed:
        msg = "institutional check failed in bundle"
    else:
        msg = "offline bundle verification passed"

    return BundleVerifyResult(
        ok=ok,
        genesis_ok=genesis.ok,
        chain_ok=chain.ok,
        lamport_ok=lamport_ok,
        bundle_sha256_ok=sha_ok,
        institutional_passed=inst_passed,
        message=msg,
        details={
            "bundle_sha256": digest,
            "entry_count": len(entries),
            "protocol": (manifest or {}).get("protocol") if isinstance(manifest, dict) else None,
            "product": (manifest or {}).get("product") if isinstance(manifest, dict) else None,
            "instance_uuid": (manifest or {}).get("instance_uuid") if isinstance(manifest, dict) else None,
        },
    )


def build_audit_bundle(
    database: Path,
    *,
    out_dir: Path | None = None,
    tarball_path: Path | None = None,
    abort_on_fail: bool = True,
    anchor_path: Path | None = None,
    repro_run: bool = False,
    product: str | None = None,
    extra_files: dict[str, Path] | None = None,
) -> AuditBundleResult:
    """
    Full P2 pipeline:
      validate → write canonical JSON files → deterministic tar → SHA256 sidecar
    """
    db = Path(database)
    out = out_dir or db.parent / "audit_bundle"
    tar_path = tarball_path or db.parent / "audit_bundle.tar"

    ledger = AppendOnlyLedger(db)
    try:
        if anchor_path is not None and Path(anchor_path).is_file():
            anchor_data = json.loads(Path(anchor_path).read_text(encoding="utf-8"))
            ledger.anchor_path.write_text(
                json.dumps(anchor_data, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        validation = validate_before_export(ledger=ledger, anchor_path=anchor_path)
        verify_dict = ledger.verify()
        ctx = build_compliance_context(ledger, run_f9=not repro_run)
        report = run_institutional_check(ledger=ledger, context=ctx, run_f9=False)

        if abort_on_fail and not validation.ok:
            return AuditBundleResult(
                ok=False,
                out_dir=out,
                tarball_path=None,
                bundle_sha256="",
                validation=validation,
                institutional_passed=report.passed,
            )
        if abort_on_fail and not repro_run and not report.passed:
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
            product=product,
            extra_files=extra_files,
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
        if product:
            sidecar["product"] = product
        (tar_path.with_suffix(tar_path.suffix + ".sha256.json")).write_text(
            json.dumps(sidecar, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (tar_path.with_suffix(tar_path.suffix + ".sha256")).write_text(
            f"{digest}  {tar_path.name}\n", encoding="utf-8"
        )
        write_signature_sidecar(tar_path, bundle_sha256=digest, product=product)

        return AuditBundleResult(
            ok=validation.ok,
            out_dir=out,
            tarball_path=tar_path,
            bundle_sha256=digest,
            validation=validation,
            institutional_passed=report.passed,
        )
    finally:
        ledger.close()


def verify_bundle_reproducible(database: Path, *, runs: int = 2) -> tuple[bool, str]:
    """F9 gate — identical state produces identical tarball hash."""
    db = Path(database)
    digests: list[str] = []
    for i in range(runs):
        out = db.parent / f"_repro_{i}"
        tar = db.parent / f"_repro_{i}.tar"
        result = build_audit_bundle(db, out_dir=out, tarball_path=tar, repro_run=True)
        if not result.ok:
            return False, f"export failed on run {i}: {result.validation.message}"
        digests.append(result.bundle_sha256)
    if len(set(digests)) != 1:
        return False, f"non-deterministic export: {digests}"
    return True, digests[0]
