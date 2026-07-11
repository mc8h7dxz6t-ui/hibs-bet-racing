"""PHI-safe observation-lane export — packet summaries only in bundle."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

from inst_spine.export import AuditBundleResult, build_audit_bundle
from inst_spine.ledger import AppendOnlyLedger


def redact_entry_for_observation_lane(entry: dict[str, Any]) -> dict[str, Any]:
    """Strip raw vitals from telemetry_batch payloads; keep cryptographic summaries."""
    out = copy.deepcopy(entry)
    payload = out.get("payload")
    if not isinstance(payload, dict) or out.get("event_type") != "telemetry_batch":
        return out
    summaries = payload.get("packet_summaries") or []
    redacted = {k: v for k, v in payload.items() if k != "packets"}
    redacted["packets_redacted"] = True
    redacted["packet_count"] = payload.get("count") or len(summaries)
    redacted["packet_summaries"] = summaries
    out["payload"] = redacted
    return out


def redact_entries_for_observation_lane(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [redact_entry_for_observation_lane(e) for e in entries]


def build_health_audit_bundle(
    database: Path,
    *,
    out_dir: Path | None = None,
    tarball_path: Path | None = None,
    observation_lane: bool = False,
    repro_run: bool = False,
    product: str = "health-telemetry",
) -> AuditBundleResult:
    """Full export; observation lane redacts raw packets in ledger_entries.json."""
    if not observation_lane:
        return build_audit_bundle(
            database,
            out_dir=out_dir,
            tarball_path=tarball_path,
            repro_run=repro_run,
            product=product,
        )

    from inst_spine.check import build_compliance_context, run_institutional_check
    from inst_spine.export import (
        _write_bundle_files,
        deterministic_tarball,
        sha256_bytes,
        validate_before_export,
    )

    db = Path(database)
    out = out_dir or db.parent / "audit_bundle_obs"
    tar_path = tarball_path or db.parent / "audit_bundle_obs.tar"

    ledger = AppendOnlyLedger(db)
    try:
        validation = validate_before_export(ledger=ledger)
        verify_dict = ledger.verify()
        ctx = build_compliance_context(ledger, run_f9=not repro_run)
        report = run_institutional_check(ledger=ledger, context=ctx, run_f9=False)

        if not validation.ok:
            return AuditBundleResult(
                ok=False,
                out_dir=out,
                tarball_path=None,
                bundle_sha256="",
                validation=validation,
                institutional_passed=report.passed,
            )
        if not repro_run and not report.passed:
            return AuditBundleResult(
                ok=False,
                out_dir=out,
                tarball_path=None,
                bundle_sha256="",
                validation=validation,
                institutional_passed=report.passed,
            )

        redacted = redact_entries_for_observation_lane(ledger.list_entries())
        report_dict = report.to_dict()
        report_dict.setdefault("extras", {})["observation_lane"] = True
        report_dict["message"] = (
            report_dict.get("message", "") + " (observation lane — PHI redacted in bundle)."
        ).strip()

        class _RedactedLedgerView:
            """Minimal view so _write_bundle_files emits redacted ledger_entries.json."""

            def __init__(self, inner: AppendOnlyLedger, entries: list[dict[str, Any]]) -> None:
                self._inner = inner
                self._entries = entries

            def list_entries(self) -> list[dict[str, Any]]:
                return self._entries

            @property
            def wal(self):
                return self._inner.wal

            @property
            def anchor_path(self) -> Path:
                return self._inner.anchor_path

            @property
            def _instance_uuid(self) -> str:
                return self._inner._instance_uuid

        view = _RedactedLedgerView(ledger, redacted)
        _write_bundle_files(
            out_dir=out,
            ledger=view,  # type: ignore[arg-type]
            validation=validation,
            report_dict=report_dict,
            verify_dict=verify_dict,
            product=product,
            observation_lane=True,
        )
        readme = out / "README.txt"
        readme.write_text(
            readme.read_text(encoding="utf-8")
            + "\nobservation_lane: true (raw packets redacted; summaries + chain intact)\n",
            encoding="utf-8",
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
            "product": product,
            "observation_lane": True,
        }
        (tar_path.with_suffix(tar_path.suffix + ".sha256.json")).write_text(
            __import__("json").dumps(sidecar, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        (tar_path.with_suffix(tar_path.suffix + ".sha256")).write_text(
            f"{digest}  {tar_path.name}\n",
            encoding="utf-8",
        )

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
