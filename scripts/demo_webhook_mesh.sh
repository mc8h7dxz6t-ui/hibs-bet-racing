#!/usr/bin/env bash
# Webhook Mesh demo — ingress → duplicate → export → verify-bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
SECRET="${WEBHOOK_PROVIDER_SECRET:-demo-secret}"
DB="${1:-./data/demo/webhook_mesh.sqlite}"
TAR="${2:-./data/demo/webhook_mesh_bundle.tar}"
BODY_FILE="$(mktemp)"
echo '{"id":"evt-demo-1"}' > "$BODY_FILE"
mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")"
export WEBHOOK_PROVIDER_SECRET="$SECRET"
export WEBHOOK_MESH_LEDGER="$DB"
export WEBHOOK_DISPATCH_MODE=background
export INST_WAL_PATH="./data/demo/webhook_mesh.wal"
SIG="$("$PYTHON" -m webhook_mesh.cli demo-sign --secret "$SECRET" --body-file "$BODY_FILE" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin)['signature'])")"
echo "── 1/4 Start server + ingress (background) ──"
"$PYTHON" -m webhook_mesh.cli serve --port 18787 --ledger "$DB" &
PID=$!
sleep 2
curl -sf -X POST "http://127.0.0.1:18787/v1/ingress/tenant-demo" \
  -H "Content-Type: application/json" \
  -H "X-Provider-Signature: $SIG" \
  -H "X-Webhook-Id: evt-demo-1" \
  -H "X-Target-Forward-Url: https://httpbin.org/post" \
  --data-binary @"$BODY_FILE" > /dev/null
curl -sf -X POST "http://127.0.0.1:18787/v1/ingress/tenant-demo" \
  -H "Content-Type: application/json" \
  -H "X-Provider-Signature: $SIG" \
  -H "X-Webhook-Id: evt-demo-1" \
  -H "X-Target-Forward-Url: https://httpbin.org/post" \
  --data-binary @"$BODY_FILE" > /dev/null || true
kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
rm -f "$BODY_FILE"
echo "── 2/4 F1–F9 check ──"
"$PYTHON" -m webhook_mesh.cli check --database "$DB"
echo "── 3/4 Export bundle ──"
"$PYTHON" -m webhook_mesh.cli export --database "$DB" --tarball "$TAR"
echo "── 4/4 Verify offline ──"
"$PYTHON" -m webhook_mesh.cli verify-bundle --tarball "$TAR"
echo "[PASS] Webhook Mesh demo → $TAR"
