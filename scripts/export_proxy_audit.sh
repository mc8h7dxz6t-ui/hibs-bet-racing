#!/usr/bin/env bash
# Proxy-Risk P2 audit export — genesis chain + deterministic tar + SHA256 sidecar.
set -euo pipefail

DB_PATH="${1:-./data/proxy_risk_ledger.sqlite}"
OUT_DIR="${2:-./proxy_audit_bundle}"
TAR_PATH="${3:-./proxy_audit_bundle.tar}"
PYTHON="${PYTHON:-python3}"

exec "$PYTHON" -m proxy_risk.cli export \
  --database "$DB_PATH" \
  --out-dir "$OUT_DIR" \
  --tarball "$TAR_PATH"
