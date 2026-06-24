#!/usr/bin/env bash
# Webhook Replay demo — capture, replay, audit bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

CAP_DIR="${1:-./data/demo/webhook_captures}"
DB="${2:-./data/demo/webhook_replay.sqlite}"
TAR="${3:-./data/demo/webhook_replay_bundle.tar}"
BODY_FILE="$(instpp_mktemp)"
mkdir -p "$CAP_DIR" "$(dirname "$DB")" "$(dirname "$TAR")"
echo '{"id":"evt-replay-1","type":"invoice.paid","amount":4200}' > "$BODY_FILE"

echo "── 1/5 Capture webhook bytes ──"
"$PYTHON" -m webhook_replay.cli capture \
  --capture-id evt-replay-1 \
  --tenant-id tenant-demo \
  --provider stripe \
  --body-file "$BODY_FILE" \
  --store-dir "$CAP_DIR" \
  --header "X-Webhook-Id:evt-replay-1"

echo "── 2/5 Air-gapped replay ──"
"$PYTHON" -m webhook_replay.cli replay \
  --capture-id evt-replay-1 \
  --store-dir "$CAP_DIR" \
  --database "$DB"

echo "── 3/5 Replay all (idempotent) ──"
"$PYTHON" -m webhook_replay.cli replay --all --store-dir "$CAP_DIR" --database "$DB"

echo "── 4/5 check ──"
"$PYTHON" -m webhook_replay.cli check --database "$DB"

echo "── 5/5 export → verify-bundle ──"
"$PYTHON" -m webhook_replay.cli export --database "$DB" --tarball "$TAR"
"$PYTHON" -m webhook_replay.cli verify-bundle --tarball "$TAR"
rm -f "$BODY_FILE"
echo "[PASS] Webhook Replay demo → $TAR"
