#!/usr/bin/env bash
# Ad Guard P2 audit export — genesis chain + deterministic tar + SHA256 sidecar.
set -euo pipefail

DB_PATH="${1:-./data/ad_guard_ledger.sqlite}"
OUT_DIR="${2:-./ad_audit_bundle}"
TAR_PATH="${3:-./ad_audit_bundle.tar}"
PYTHON="${PYTHON:-python3}"

exec "$PYTHON" -m inst_spine.export_cli "$DB_PATH" --out-dir "$OUT_DIR" --tarball "$TAR_PATH"
