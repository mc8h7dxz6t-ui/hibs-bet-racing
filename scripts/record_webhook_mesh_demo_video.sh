#!/usr/bin/env bash
# Guided Webhook Mesh demo for screen-recording — pauses for narration.
# Usage: ./scripts/record_webhook_mesh_demo_video.sh
# Read aloud: docs/DEMO_VIDEO_WEBHOOK_MESH.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"

SECRET="${WEBHOOK_PROVIDER_SECRET:-demo-secret}"
DB="${WEBHOOK_MESH_RECORD_DB:-./data/demo/webhook_mesh_video.sqlite}"
TAR="${WEBHOOK_MESH_RECORD_TAR:-./data/demo/webhook_mesh_video_bundle.tar}"
PORT="${WEBHOOK_MESH_RECORD_PORT:-18787}"
BODY_FILE="$(instpp_mktemp)"
EVENT_ID="evt-video-demo-1"

mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")"
echo '{"id":"evt-video-demo-1","type":"checkout.session.completed"}' > "$BODY_FILE"

export WEBHOOK_PROVIDER_SECRET="$SECRET"
export WEBHOOK_MESH_LEDGER="$DB"
export WEBHOOK_DISPATCH_MODE=background
export INST_WAL_PATH="./data/demo/webhook_ingress_video.wal"

_sign() {
  local provider="$1"
  "$PYTHON" -m webhook_mesh.cli demo-sign --secret "$SECRET" --provider "$provider" --body-file "$BODY_FILE"
}

_pause() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  [PAUSE] $1"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  read -r -p "  Press Enter when ready to continue… "
  echo ""
}

_cleanup() {
  if [[ -n "${SERVER_PID:-}" ]]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -f "$BODY_FILE"
}
trap _cleanup EXIT

_pause "SAY: Hook — 'What if Stripe sends the same event twice?'"

echo "── Starting webhook-mesh server on port $PORT ──"
"$PYTHON" -m webhook_mesh.cli serve --port "$PORT" --ledger "$DB" &
SERVER_PID=$!
sleep 2

_pause "SAY: First Stripe event — valid signature — should ACCEPT (200)"

STRIPE_SIG=$(_sign stripe | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin)['signature'])")
echo "POST /v1/ingress/stripe/tenant-demo (first delivery)"
curl -sS -w "\n  HTTP %{http_code}\n" -X POST "http://127.0.0.1:$PORT/v1/ingress/stripe/tenant-demo" \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: $STRIPE_SIG" \
  -H "Stripe-Event-Id: $EVENT_ID" \
  -H "X-Target-Forward-Url: https://httpbin.org/post" \
  --data-binary @"$BODY_FILE" || true

_pause "SAY: SAME event ID again — should REJECT duplicate (409 or 200 already-processed — not double-charge)"

echo "POST /v1/ingress/stripe/tenant-demo (duplicate — same Stripe-Event-Id)"
curl -sS -w "\n  HTTP %{http_code}\n" -X POST "http://127.0.0.1:$PORT/v1/ingress/stripe/tenant-demo" \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: $STRIPE_SIG" \
  -H "Stripe-Event-Id: $EVENT_ID" \
  -H "X-Target-Forward-Url: https://httpbin.org/post" \
  --data-binary @"$BODY_FILE" || true

_pause "SAY: Bad signature — should FAIL CLOSED (401)"

echo "POST with invalid Stripe-Signature"
curl -sS -w "\n  HTTP %{http_code}\n" -X POST "http://127.0.0.1:$PORT/v1/ingress/stripe/tenant-demo" \
  -H "Content-Type: application/json" \
  -H "Stripe-Signature: t=0,v1=deadbeef" \
  -H "Stripe-Event-Id: evt-bad-sig" \
  -H "X-Target-Forward-Url: https://httpbin.org/post" \
  --data-binary @"$BODY_FILE" || true

kill "$SERVER_PID" 2>/dev/null || true
wait "$SERVER_PID" 2>/dev/null || true
SERVER_PID=""

_pause "SAY: Export + offline verify — auditor replay without live DB"

echo "── check → export → verify-bundle ──"
"$PYTHON" -m webhook_mesh.cli check --database "$DB"
"$PYTHON" -m webhook_mesh.cli export --database "$DB" --tarball "$TAR"
"$PYTHON" -m webhook_mesh.cli verify-bundle --tarball "$TAR"

echo ""
echo "[PASS] Recording demo complete → $TAR"
_pause "SAY: CTA — VPC pilot from £2.5k · DM for 15-min live dry-run"
