#!/usr/bin/env bash
# Compliance Logger demo — ingest → check → export → offline verify.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
DB="${1:-./data/demo/compliance.sqlite}"
OUT="${2:-./data/demo/compliance_bundle}"
TAR="${3:-./data/demo/compliance_bundle.tar}"

mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")" "$OUT"

step() { echo ""; echo "── $* ──"; }

echo "Compliance Logger (#1)"
echo "  database: $DB"
echo "  bundle:   $TAR"

step "1/5 Ingest decision (snapshot + outcome)"
"$PYTHON" -m compliance_log.cli ingest \
  --snapshot docs/demo_snapshot.json \
  --outcome '{"status":"approved","ref":"demo-001","policy":"kyc_tier_2"}' \
  --actor demo-auditor \
  --database "$DB" | "$PYTHON" -c "
import sys, json
e = json.load(sys.stdin)
print(f\"  entry_id: {e['entry_id'][:16]}...\")
print(f\"  event:    {e['event_type']} | lamport {e['lamport_seq']}\")
"

step "2/5 Verify hash chain"
"$PYTHON" -m compliance_log.cli verify-chain --database "$DB" | "$PYTHON" -c "
import sys, json
v = json.load(sys.stdin)
assert v['chain_ok'] and v['genesis_ok']
print(f\"  chain_ok: {v['chain_ok']} | entries: {v['entries_checked']}\")
"

step "3/5 Institutional check (F1–F9)"
"$PYTHON" -m compliance_log.cli check --database "$DB" | "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
assert r['passed'], r
gates = [c['name'] for c in r['checks'] if c['passed']]
print(f\"  passed: {r['passed']} | gates: {', '.join(gates)}\")
"

step "4/5 Export audit bundle (deterministic tar + SHA256)"
"$PYTHON" -m compliance_log.cli export \
  --database "$DB" \
  --out-dir "$OUT" \
  --tarball "$TAR" | "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
assert r['ok'], r
print(f\"  sha256: {r['bundle_sha256'][:16]}...\")
print(f\"  product: {r.get('product', 'compliance-logger')}\")
"

step "5/5 Offline auditor verify-bundle"
"$PYTHON" -m compliance_log.cli verify-bundle --tarball "$TAR" | "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
assert r['ok'], r
print(f\"  offline_ok: {r['ok']} | chain: {r['chain_ok']} | F9 bundle: {r['bundle_sha256_ok']}\")
"

echo ""
echo "[PASS] Compliance Logger demo"
echo "       Proof: $TAR"
