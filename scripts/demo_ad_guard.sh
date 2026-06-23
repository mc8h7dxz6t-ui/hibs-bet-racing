#!/usr/bin/env bash
# Ad Guard demo — evaluate → check → export → verify-bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
DB="${1:-./data/demo/ad_guard.sqlite}"
TAR="${2:-./data/demo/ad_guard_bundle.tar}"
mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")"
BODY='{"campaignId":"12345","bidMicros":2500000,"costMicros":10000000}'
echo "── 1/4 Shadow evaluate (Google spend) ──"
"$PYTHON" -m ad_guard.cli evaluate --provider google --body "$BODY" --database "$DB" || true
echo "── 2/4 F1–F9 check ──"
"$PYTHON" -m ad_guard.cli check --database "$DB"
echo "── 3/4 Export bundle ──"
"$PYTHON" -m ad_guard.cli export --database "$DB" --tarball "$TAR"
echo "── 4/4 Verify offline ──"
"$PYTHON" -m ad_guard.cli verify-bundle --tarball "$TAR"
echo "[PASS] Ad Guard demo → $TAR"
