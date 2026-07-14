#!/usr/bin/env bash
# Agent Ledger demo — shadow → permit → complete → deny → escalate → export → verify.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

DB="${1:-./data/demo/agent_ledger.sqlite}"
PERMIT_DB="${2:-./data/demo/agent_ledger_permits.sqlite}"
TAR="${3:-./data/demo/agent_ledger_bundle.tar}"
mkdir -p "$(dirname "$DB")" "$(dirname "$PERMIT_DB")" "$(dirname "$TAR")"
rm -f "$DB" "$PERMIT_DB"

echo "── 1/7 Shadow burn-in (log only) ──"
"$PYTHON" -m agent_ledger.cli authorize \
  --agent-id demo-agent --tool http_post \
  --args '{"url":"https://api.example.com/ping"}' \
  --database "$DB" --permit-db "$PERMIT_DB" --shadow || true

echo "── 2/7 Permit low-risk tool ──"
AUTH=$("$PYTHON" -m agent_ledger.cli authorize \
  --agent-id demo-agent --tool read_file \
  --args '{"path":"docs/demo_snapshot.json"}' \
  --database "$DB" --permit-db "$PERMIT_DB" \
  --idempotency-key permit-demo-1)
PERMIT_ID=$(echo "$AUTH" | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('permit_id',''))")

echo "── 3/7 Complete with result attestation ──"
"$PYTHON" -m agent_ledger.cli complete \
  --permit-id "$PERMIT_ID" \
  --result '{"bytes_read":1024,"status":"ok"}' \
  --database "$DB" --permit-db "$PERMIT_DB"

echo "── 4/7 Deny forbidden args ──"
"$PYTHON" -m agent_ledger.cli authorize \
  --agent-id demo-agent --tool sql_select \
  --args '{"query":"DROP TABLE users"}' \
  --database "$DB" --permit-db "$PERMIT_DB" || true

echo "── 5/7 Escalate critical without human (break-glass tier) ──"
echo '{"agent_tier":"break_glass","require_human_for_critical":true}' > "$(dirname "$DB")/escalate_policy.json"
"$PYTHON" -m agent_ledger.cli authorize \
  --agent-id break-glass-agent --tool transfer_funds \
  --args '{"amount":5000,"currency":"GBP"}' \
  --database "$DB" --permit-db "$PERMIT_DB" \
  --policy-file "$(dirname "$DB")/escalate_policy.json" || true

echo "── 6/7 Permit critical with human approval ──"
POLICY_FILE="$(dirname "$DB")/break_glass_policy.json"
echo '{"agent_tier":"break_glass","require_human_for_critical":true}' > "$POLICY_FILE"
AUTH2=$("$PYTHON" -m agent_ledger.cli authorize \
  --agent-id break-glass-agent --tool deploy_service \
  --args '{"service":"payments-api","human_approved":true,"ticket":"INC-42"}' \
  --database "$DB" --permit-db "$PERMIT_DB" \
  --policy-file "$POLICY_FILE")
echo "$AUTH2"

echo "── 7/7 check → export → verify-bundle ──"
"$PYTHON" -m agent_ledger.cli check --database "$DB"
"$PYTHON" -m agent_ledger.cli export --database "$DB" --tarball "$TAR"
"$PYTHON" -m agent_ledger.cli verify-bundle --tarball "$TAR"
echo "[PASS] Agent Ledger demo → $TAR"
