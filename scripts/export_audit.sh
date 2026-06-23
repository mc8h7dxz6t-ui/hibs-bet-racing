#!/usr/bin/env bash
# Inst++ P2 audit export — validate chain, deterministic tar, SHA256 sidecar.
set -euo pipefail

DB_PATH="${1:-./data/inst_ledger.sqlite}"
OUT_DIR="${2:-./audit_bundle}"
TAR_PATH="${3:-./audit_bundle.tar}"
PYTHON="${PYTHON:-python3}"

exec "$PYTHON" -m inst_spine.export_cli "$DB_PATH" --out-dir "$OUT_DIR" --tarball "$TAR_PATH"
