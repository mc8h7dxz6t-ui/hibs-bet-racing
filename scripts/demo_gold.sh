#!/usr/bin/env bash
# Canonical spend-plane sales walkthrough — 12 steps, CLI + HTTP gateway (Spend Guard).
#
# Shipped proof for LLM spend governance: reserve-before-dispatch, settle, drift lockout,
# offline verify-bundle. Postgres compose stack is a design-partner north star — not required here.
#
# Usage:
#   make demo-gold
#   make demo-gold-reset && make demo-gold   # after wallet locked in step 10
#
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
_GOLD_DIR_OVERRIDE="${GOLD_DEMO_DIR:-}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

GOLD_DIR="${_GOLD_DIR_OVERRIDE:-${GOLD_DEMO_DIR:-./data/demo/spend_gold}}"
WALLET_DB="$GOLD_DIR/spend_wallet.sqlite"
LEDGER_DB="$GOLD_DIR/spend_guard.sqlite"
TAR="$GOLD_DIR/spend_guard_bundle.tar"

mkdir -p "$GOLD_DIR"

step() {
  echo ""
  echo "══════════════════════════════════════════════════════════════"
  printf "  STEP %2s/11 — %s\n" "$1" "$2"
  echo "══════════════════════════════════════════════════════════════"
  echo "  $3"
  echo ""
}

reserve() {
  local rid="$1" cost="$2"
  shift 2
  "$PYTHON" -m spend_guard.cli reserve \
    --request-id "$rid" --cost "$cost" \
    --wallet-db "$WALLET_DB" --ledger-db "$LEDGER_DB" "$@"
}

settle() {
  local hold="$1" rid="$2" actual="$3"
  "$PYTHON" -m spend_guard.cli settle \
    --hold-id "$hold" --request-id "$rid" --actual-cost "$actual" \
    --wallet-db "$WALLET_DB" --ledger-db "$LEDGER_DB"
}

hold_from_json() {
  "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('hold_id',''))"
}

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  GOLD DEMO — Spend Guard (reserve → settle → drift lockout)  ║"
echo "╚══════════════════════════════════════════════════════════════╝"

pip install -e ".[dev,instpp]" -q

step 1 "Init budget" \
  "Platform wallet seeded with £1000 — every reserve is logged before dispatch."

rm -f "$WALLET_DB" "$LEDGER_DB" "$TAR"
"$PYTHON" -m spend_guard.cli init-wallet --wallet-db "$WALLET_DB" --balance 1000

step 2 "Shadow burn-in" \
  "Shadow reserve — gateway semantics without debiting (Proxy-Risk style burn-in)."

reserve shadow-openai-1 40 --shadow | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); assert d.get('decision')=='approve', d"

step 3 "Provider A — reserve" \
  "Reserve estimated cost before calling OpenAI-compatible endpoint."

R1=$(reserve openai-gpt4o-mini-1 30)
H1=$(echo "$R1" | hold_from_json)

step 4 "Provider A — settle" \
  "Settle actual tokens — estimate vs actual reconciled on ledger."

settle "$H1" openai-gpt4o-mini-1 28.5 >/dev/null

step 5 "Provider B — reserve" \
  "Second provider route — same wallet, shared drift baseline."

R2=$(reserve anthropic-claude-1 45)
H2=$(echo "$R2" | hold_from_json)

step 6 "Provider B — settle" \
  "Settle Anthropic call — running balance updated."

settle "$H2" anthropic-claude-1 44.2 >/dev/null

step 7 "Reconciler variance" \
  "Actual below estimate — unused hold released; ledger records true cost."

R3=$(reserve google-gemini-1 30)
H3=$(echo "$R3" | hold_from_json)
settle "$H3" google-gemini-1 22.4 >/dev/null

step 8 "Wallet status" \
  "FinOps view — balance, holds, drift % before next dispatch."

"$PYTHON" -m spend_guard.cli status --wallet-db "$WALLET_DB"

step 9 "Normal traffic" \
  "Healthy reserve → settle cycle continues until drift threshold."

R4=$(reserve openai-gpt4o-mini-2 18)
H4=$(echo "$R4" | hold_from_json)
settle "$H4" openai-gpt4o-mini-2 17.5 >/dev/null

step 10 "Drift lockout" \
  "DRIFT_THRESHOLD_EXCEEDED → wallet locked → next reserve returns locked/409 semantics."

export WALLET_DB="$WALLET_DB" LEDGER_DB="$LEDGER_DB"
"$PYTHON" - <<'PY'
import json
import os
from pathlib import Path

from inst_spine.ledger import AppendOnlyLedger
from spend_guard.gateway import SpendGuardGateway, SpendRequest
from spend_guard.wallet import SpendWallet

wallet_db = Path(os.environ["WALLET_DB"])
ledger_db = Path(os.environ["LEDGER_DB"])
wallet = SpendWallet(wallet_db, drift_threshold_pct=0.35)
ledger = AppendOnlyLedger(ledger_db)
gw = SpendGuardGateway(wallet=wallet, ledger=ledger)

# Establish rolling baseline in-process (history is per gateway session).
for i in range(6):
    rid = f"drift-baseline-{i}"
    r = gw.reserve(SpendRequest(request_id=rid, estimated_cost=22.0))
    if r.hold_id:
        gw.settle(r.hold_id, actual_cost=22.0, request_id=rid)

# Spike above threshold → lock on settle.
r = gw.reserve(SpendRequest(request_id="drift-spike", estimated_cost=180.0))
if r.hold_id:
    s = gw.settle(r.hold_id, actual_cost=180.0, request_id="drift-spike")
    print(json.dumps({"spike_settle": s.to_dict()}, indent=2))

blocked = gw.reserve(SpendRequest(request_id="drift-blocked", estimated_cost=5.0))
print(json.dumps({"blocked_reserve": blocked.to_dict()}, indent=2))
PY

LOCKED=$("$PYTHON" -m spend_guard.cli status --wallet-db "$WALLET_DB" \
  | "$PYTHON" -c "import sys,json; print(json.load(sys.stdin).get('wallet',{}).get('locked', False))")
echo "  wallet locked after drift drill: $LOCKED"

step 11 "Audit surface" \
  "F1–F9 check → deterministic export → offline verify-bundle (auditor never calls vendor)."

"$PYTHON" -m spend_guard.cli check --database "$LEDGER_DB"
"$PYTHON" -m spend_guard.cli export --database "$LEDGER_DB" --tarball "$TAR"
"$PYTHON" -m spend_guard.cli verify-bundle --tarball "$TAR"

step 12 "HTTP gateway" \
  "OpenAI-compat serve — reserve/settle on HTTP path (production ingress proof)."

export SPEND_GUARD_WALLET_DB="$WALLET_DB"
export SPEND_GUARD_LEDGER_DB="$LEDGER_DB"
export SPEND_GUARD_MOCK_UPSTREAM=1
unset SPEND_GUARD_API_KEY
"$PYTHON" - <<'PY'
import json
import os

from fastapi.testclient import TestClient
import spend_guard.serve as serve_mod

serve_mod.state.wallet_db = os.environ["SPEND_GUARD_WALLET_DB"]
serve_mod.state.ledger_db = os.environ["SPEND_GUARD_LEDGER_DB"]
serve_mod.state.mock_upstream = True
serve_mod.state.gateway = None

client = TestClient(serve_mod.app)
assert client.get("/ready").json()["ready"] is True
r = client.post(
    "/v1/chat/completions",
    json={
        "model": "demo-model",
        "messages": [{"role": "user", "content": "gold demo HTTP"}],
        "max_tokens": 8,
    },
    headers={"X-Request-Id": "gold-http-1"},
)
assert r.status_code == 200, r.text
if serve_mod.state.ledger:
    serve_mod.state.ledger.stop_async_writer(flush=True)
print(json.dumps({"gold_http_gateway": "ok"}))
PY

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║  GOLD DEMO COMPLETE — 12/12 steps (CLI + HTTP gateway)       ║"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""
echo "  Bundle:  $TAR"
echo "  Reset:   make demo-gold-reset && make demo-gold"
echo "  All 11:  make demo-all"
echo "  UI:      make demo-gold-up  → http://127.0.0.1:8790 (Compliance + Proxy)"
echo ""
