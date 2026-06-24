#!/usr/bin/env bash
# Webhook Mesh demo — generic + Stripe + Shopify ingress signatures.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
SECRET="${WEBHOOK_PROVIDER_SECRET:-demo-secret}"
DB="${1:-./data/demo/webhook_mesh_ledger.sqlite}"
TAR="${2:-./data/demo/webhook_mesh_bundle.tar}"
BODY_FILE="$(instpp_mktemp)"
echo '{"id":"evt-demo-1","type":"checkout.session.completed"}' > "$BODY_FILE"
mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")"
export WEBHOOK_PROVIDER_SECRET="$SECRET"
export WEBHOOK_MESH_LEDGER="$DB"
export WEBHOOK_DISPATCH_MODE=background
export INST_WAL_PATH="./data/demo/webhook_ingress.wal"

_sign() {
  local provider="$1"
  "$PYTHON" -m webhook_mesh.cli demo-sign --secret "$SECRET" --provider "$provider" --body-file "$BODY_FILE"
}

echo "── 1/5 Start server (background) ──"
"$PYTHON" -m webhook_mesh.cli serve --port 18787 --ledger "$DB" &
PID=$!
sleep 2

echo "── 2/5 Generic ingress ──"
SIG=$(_sign generic | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin)['signature'])")
curl -sf -X POST "http://127.0.0.1:18787/v1/ingress/tenant-demo" \
  -H "Content-Type: application/json" \
  -H "X-Provider-Signature: $SIG" \
  -H "X-Webhook-Id: evt-demo-generic" \
  -H "X-Target-Forward-Url: https://httpbin.org/post" \
  --data-binary @"$BODY_FILE" > /dev/null || true

echo "── 3/5 Stripe route ──"
STRIPE_SIG=$(_sign stripe | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin)['signature'])")
curl -sf -X POST "http://127.0.0.1:18787/v1/ingress/stripe/tenant-demo" \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: $STRIPE_SIG" \
  -H "Stripe-Event-Id: evt-demo-stripe" \
  -H "X-Target-Forward-Url: https://httpbin.org/post" \
  --data-binary @"$BODY_FILE" > /dev/null || true

echo "── 4/5 Shopify route ──"
SHOPIFY_SIG=$(_sign shopify | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin)['signature'])")
curl -sf -X POST "http://127.0.0.1:18787/v1/ingress/shopify/tenant-demo" \
  -H "Content-Type: application/json" \
  -H "X-Shopify-Hmac-Sha256: $SHOPIFY_SIG" \
  -H "X-Shopify-Webhook-Id: evt-demo-shopify" \
  -H "X-Target-Forward-Url: https://httpbin.org/post" \
  --data-binary @"$BODY_FILE" > /dev/null || true

kill "$PID" 2>/dev/null || true
wait "$PID" 2>/dev/null || true
rm -f "$BODY_FILE"

echo "── 5/5 check → export → verify ──"
"$PYTHON" -m webhook_mesh.cli check --database "$DB"
"$PYTHON" -m webhook_mesh.cli export --database "$DB" --tarball "$TAR"
"$PYTHON" -m webhook_mesh.cli verify-bundle --tarball "$TAR"
echo "[PASS] Webhook Mesh demo → $TAR"
