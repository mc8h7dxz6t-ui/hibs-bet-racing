#!/usr/bin/env bash
# One-command Proxy-Risk demo — shadow → live forward → check → export → verify.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
DB="${1:-./data/demo_proxy.sqlite}"
OUT="${2:-./demo_proxy_audit}"
TAR="${3:-./demo_proxy_audit.tar}"

echo "==> Proxy-Risk Gateway demo"
echo "    database: $DB"
echo "    tarball:  $TAR"

REQ="$(cat docs/demo_proxy_request.json)"
BODY="$(echo "$REQ" | "$PYTHON" -c "import sys,json; print(json.dumps(json.load(sys.stdin)['body']))")"

"$PYTHON" -m proxy_risk.cli evaluate \
  --client-id broker-demo \
  --method POST \
  --path /orders \
  --body "$BODY" \
  --idempotency-key demo-shadow-1 \
  --database "$DB"

export PROXY_RISK_UPSTREAM_BASE="${PROXY_RISK_UPSTREAM_BASE:-https://httpbin.org}"
"$PYTHON" -m proxy_risk.cli evaluate \
  --live \
  --client-id broker-demo \
  --method POST \
  --path /post \
  --body '{"demo":"proxy-risk-live"}' \
  --idempotency-key demo-live-1 \
  --database "$DB"

"$PYTHON" -m proxy_risk.cli check --database "$DB"
"$PYTHON" -m proxy_risk.cli export \
  --database "$DB" \
  --out-dir "$OUT" \
  --tarball "$TAR"
"$PYTHON" -m proxy_risk.cli verify-bundle --tarball "$TAR"

echo ""
echo "PROXY-RISK DEMO PASSED"
echo "Proof artifacts: $TAR (+ .sha256 sidecar)"
