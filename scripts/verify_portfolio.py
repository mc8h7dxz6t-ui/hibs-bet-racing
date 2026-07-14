#!/usr/bin/env python3
"""Offline verify-bundle for all 12 portfolio tarballs — auditor never calls vendor."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from inst_spine.export import verify_audit_bundle
from inst_workflow.catalog import PRODUCT_CATALOG


def main() -> int:
    demo_dir = Path(os.environ.get("PORTFOLIO_DEMO_DIR", "data/demo/portfolio"))
    results: list[dict] = []
    failed = 0

    for entry in PRODUCT_CATALOG:
        tar = demo_dir / f"{entry.bundle_name}.tar"
        row: dict = {
            "id": entry.id,
            "sku": entry.sku,
            "cli": entry.cli,
            "tarball": str(tar),
            "present": tar.is_file(),
        }
        if not tar.is_file():
            row.update({"ok": False, "message": "tarball missing — run: make demo-all"})
            failed += 1
            results.append(row)
            continue

        verify = verify_audit_bundle(tar)
        row.update(
            {
                "ok": verify.ok,
                "genesis_ok": verify.genesis_ok,
                "chain_ok": verify.chain_ok,
                "lamport_ok": verify.lamport_ok,
                "bundle_sha256_ok": verify.bundle_sha256_ok,
                "institutional_passed": verify.institutional_passed,
                "message": verify.message,
            }
        )
        if not verify.ok:
            failed += 1
        results.append(row)

    manifest = {
        "suite": "verify_portfolio",
        "status": "PASSED" if failed == 0 else "FAILED",
        "products": len(PRODUCT_CATALOG),
        "verified_ok": sum(1 for r in results if r.get("ok")),
        "finished_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "demo_dir": str(demo_dir),
        "results": results,
    }

    demo_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = demo_dir / "PORTFOLIO_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(manifest, indent=2))
    if failed:
        print(f"\n[FAIL] {failed} bundle(s) failed offline verify", file=sys.stderr)
        return 1
    print(f"\n[OK] 12/12 offline verify-bundle PASSED → {manifest_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
