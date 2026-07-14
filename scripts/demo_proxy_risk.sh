#!/usr/bin/env bash
# Proxy-Risk demo — shadow → live forward → check → export → verify.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap
DB="${1:-./data/demo/proxy.sqlite}"
OUT="${2:-./data/demo/proxy_bundle}"
TAR="${3:-./data/demo/proxy_bundle.tar}"
SKIP_LIVE="${SKIP_LIVE:-0}"

mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")" "$OUT"

parse_json_objects() {
  "$PYTHON" -c "
import sys, json
text = sys.stdin.read()
dec = json.JSONDecoder()
idx = 0
objs = []
while idx < len(text):
    while idx < len(text) and text[idx].isspace():
        idx += 1
    if idx >= len(text):
        break
    obj, end = dec.raw_decode(text, idx)
    objs.append(obj)
    idx = end
json.dump(objs, sys.stdout)
"
}

step() { echo ""; echo "── $* ──"; }

BODY="$("$PYTHON" -c "import json; print(json.dumps(json.load(open('docs/demo_proxy_request.json'))['body']))")"

echo "Proxy-Risk Gateway (#2)"
echo "  database: $DB"
echo "  bundle:   $TAR"
echo "  skip_live: $SKIP_LIVE"

step "1/6 Shadow evaluate (gates only, no upstream)"
"$PYTHON" -m proxy_risk.cli evaluate \
  --client-id broker-demo \
  --method POST \
  --path /orders \
  --body "$BODY" \
  --idempotency-key demo-shadow-1 \
  --database "$DB" | parse_json_objects | "$PYTHON" -c "
import sys, json
objs = json.load(sys.stdin)
resp = objs[0]
assert resp['decision'] == 'approve', resp
print(f\"  decision: {resp['decision']} | reason: {resp['reason']}\")
"

step "2/6 Idempotency duplicate (in-process proof)"
"$PYTHON" - <<'PY'
import asyncio, json
from inst_spine.rates import MemoryIdempotencyBackend
from proxy_risk.router import GateDecision, ProxyRequest, ProxyRiskGateway

async def main():
    gw = ProxyRiskGateway(shadow_mode=True, idempotency=MemoryIdempotencyBackend())
    req = ProxyRequest(client_id="demo", method="POST", path="/x", body={}, idempotency_key="dup")
    r1 = await gw.evaluate(req)
    r2 = await gw.evaluate(req)
    assert r1.decision == GateDecision.APPROVE and r2.decision == GateDecision.REJECT
    print(f"  first: {r1.decision.value} | duplicate: {r2.decision.value}")

asyncio.run(main())
PY

if [[ "$SKIP_LIVE" == "1" ]]; then
  step "3/6 Live forward — SKIPPED (SKIP_LIVE=1)"
  echo "  (set SKIP_LIVE=0 for httpbin live forward)"
else
  step "3/6 Live forward (httpbin.org — fail-closed on errors)"
  export PROXY_RISK_UPSTREAM_BASE="${PROXY_RISK_UPSTREAM_BASE:-https://httpbin.org}"
  "$PYTHON" -m proxy_risk.cli evaluate \
    --live \
    --client-id broker-demo \
    --method POST \
    --path /post \
    --body '{"demo":"proxy-risk-live","product":"instpp"}' \
    --idempotency-key demo-live-1 \
    --database "$DB" | parse_json_objects | "$PYTHON" -c "
import sys, json
resp = json.load(sys.stdin)[0]
assert resp['decision'] == 'approve' and resp.get('upstream_status') == 200, resp
print(f\"  decision: {resp['decision']} | upstream: {resp['upstream_status']}\")
"
fi

step "4/6 Institutional check (F1–F9)"
"$PYTHON" -m proxy_risk.cli check --database "$DB" | "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
assert r['passed'], r
print(f\"  passed: {r['passed']} | message: {r['message']}\")
"

step "5/6 Export audit bundle"
"$PYTHON" -m proxy_risk.cli export \
  --database "$DB" \
  --out-dir "$OUT" \
  --tarball "$TAR" | "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
assert r['ok'], r
print(f\"  sha256: {r['bundle_sha256'][:16]}... | product: {r.get('product')}\")
"

step "6/6 Offline auditor verify-bundle"
"$PYTHON" -m proxy_risk.cli verify-bundle --tarball "$TAR" | "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
assert r['ok'], r
print(f\"  offline_ok: {r['ok']} | institutional: {r['institutional_passed']}\")
"

echo ""
echo "[PASS] Proxy-Risk demo"
echo "       Proof: $TAR"
