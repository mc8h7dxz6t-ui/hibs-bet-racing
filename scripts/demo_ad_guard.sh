#!/usr/bin/env bash
# Ad Guard demo — evaluate with optional NeMo creative approval gate.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap
DB="${1:-./data/demo/ad_guard.sqlite}"
TAR="${2:-./data/demo/ad_guard_bundle.tar}"
mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")"
BODY='{"campaignId":"12345","bidMicros":2500000,"costMicros":10000000}'
echo "── 1/5 Shadow evaluate (Google spend) ──"
"$PYTHON" -m ad_guard.cli evaluate --provider google --body "$BODY" --database "$DB" || true
if [ "${AD_GUARD_REQUIRE_CREATIVE_APPROVAL:-0}" = "1" ]; then
  echo "── 2/5 NeMo gate ON — without approval (expect reject) ──"
  AD_GUARD_REQUIRE_CREATIVE_APPROVAL=1 "$PYTHON" -m ad_guard.cli evaluate \
    --provider google --body "$BODY" --database "$DB" || true
  echo "── 3/5 NeMo gate ON — with --creative-approved ──"
  AD_GUARD_REQUIRE_CREATIVE_APPROVAL=1 "$PYTHON" -m ad_guard.cli evaluate \
    --provider google --body "$BODY" --database "$DB" --creative-approved || true
else
  echo "── 2/5 NeMo creative gate (set AD_GUARD_REQUIRE_CREATIVE_APPROVAL=1 to demo) ──"
  echo "── 3/5 Approved spend with --creative-approved ──"
  "$PYTHON" -m ad_guard.cli evaluate \
    --provider google --body "$BODY" --database "$DB" --creative-approved || true
fi
echo "── 4/5 F1–F9 check → export → verify ──"
"$PYTHON" -m ad_guard.cli check --database "$DB"
"$PYTHON" -m ad_guard.cli export --database "$DB" --tarball "$TAR"
"$PYTHON" -m ad_guard.cli verify-bundle --tarball "$TAR"
echo "[PASS] Ad Guard demo → $TAR"
