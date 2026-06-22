#!/usr/bin/env bash
# One-command Compliance Logger demo — ingest → check → export → offline verify.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
DB="${1:-./data/demo_compliance.sqlite}"
OUT="${2:-./demo_compliance_audit}"
TAR="${3:-./demo_compliance_audit.tar}"

echo "==> Compliance Logger demo"
echo "    database: $DB"
echo "    tarball:  $TAR"

"$PYTHON" -m compliance_log.cli ingest \
  --snapshot docs/demo_snapshot.json \
  --outcome '{"status":"approved","ref":"demo-001"}' \
  --actor demo-auditor \
  --database "$DB"

"$PYTHON" -m compliance_log.cli verify-chain --database "$DB"
"$PYTHON" -m compliance_log.cli check --database "$DB"
"$PYTHON" -m compliance_log.cli export \
  --database "$DB" \
  --out-dir "$OUT" \
  --tarball "$TAR"
"$PYTHON" -m compliance_log.cli verify-bundle --tarball "$TAR"

echo ""
echo "COMPLIANCE LOGGER DEMO PASSED"
echo "Proof artifacts: $TAR (+ .sha256 sidecar)"
