#!/usr/bin/env bash
# Spend Guard demo — reserve/settle, drift lockout, audit bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

WALLET_DB="${1:-./data/demo/spend_guard_wallet.sqlite}"
DB="${2:-./data/demo/spend_guard.sqlite}"
TAR="${3:-./data/demo/spend_guard_bundle.tar}"
mkdir -p "$(dirname "$WALLET_DB")" "$(dirname "$DB")" "$(dirname "$TAR")"

echo "── 1/6 Init wallet ──"
rm -f "$WALLET_DB" "$DB"
"$PYTHON" -m spend_guard.cli init-wallet --wallet-db "$WALLET_DB" --balance 1000

echo "── 2/6 Reserve → settle (normal spend) ──"
RESERVE=$("$PYTHON" -m spend_guard.cli reserve \
  --request-id req-normal-1 --cost 25 \
  --wallet-db "$WALLET_DB" --ledger-db "$DB")
HOLD_ID=$(echo "$RESERVE" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('hold_id',''))")
"$PYTHON" -m spend_guard.cli settle \
  --hold-id "$HOLD_ID" --request-id req-normal-1 --actual-cost 24 \
  --wallet-db "$WALLET_DB" --ledger-db "$DB"

echo "── 3/6 Drift lockout drill ──"
"$PYTHON" -m spend_guard.cli demo-drift-lock \
  --wallet-db "$WALLET_DB" --ledger-db "$DB" --spend 50 --big-spend 300 --iterations 6 || true

echo "── 4/6 Status ──"
"$PYTHON" -m spend_guard.cli status --wallet-db "$WALLET_DB"

echo "── 5/6 check ──"
"$PYTHON" -m spend_guard.cli check --database "$DB"

echo "── 6/6 export → verify-bundle ──"
"$PYTHON" -m spend_guard.cli export --database "$DB" --tarball "$TAR"
"$PYTHON" -m spend_guard.cli verify-bundle --tarball "$TAR"
echo "[PASS] Spend Guard demo → $TAR"
