#!/usr/bin/env bash
# Rigorous Inst++ E2E test — Compliance Logger (#1) + Proxy-Risk Gateway (#2).
# Logs full output to logs/instpp_rigorous_<timestamp>.log
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
TS="$(date -u +%Y-%m-%dT%H%M%SZ)"
LOG_DIR="$ROOT/docs/test_logs"
LOG_FILE="$LOG_DIR/instpp_rigorous_${TS}.log"
LATEST_LINK="$LOG_DIR/instpp_rigorous_latest.log"

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "================================================================"
echo "INST++ RIGOROUS TEST — Compliance Logger + Proxy-Risk Gateway"
echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ) UTC"
echo "Log: $LOG_FILE"
echo "================================================================"

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*"; exit 1; }

# Parse one or more pretty-printed JSON objects from CLI stdout.
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

section() {
  echo ""
  echo "----------------------------------------------------------------"
  echo "SECTION: $*"
  echo "----------------------------------------------------------------"
}

section "Install dependencies"
pip install -e ".[dev,instpp]" -q

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
COMPLIANCE_DB="$WORK/compliance.sqlite"
PROXY_DB="$WORK/proxy.sqlite"
COMPLIANCE_TAR="$WORK/compliance_bundle.tar"
PROXY_TAR="$WORK/proxy_bundle.tar"
echo "Work dir: $WORK"

section "Unit tests — Compliance + Proxy-Risk"
"$PYTHON" -m pytest \
  tests/test_inst_spine_core.py \
  tests/test_inst_export.py \
  tests/test_inst_products.py \
  tests/test_proxy_risk.py \
  -v --tb=short
pass "Unit test suite"

section "Compliance Logger — ingest + chain"
"$PYTHON" -m compliance_log.cli ingest \
  --snapshot docs/demo_snapshot.json \
  --outcome '{"status":"approved","ref":"rigorous-001"}' \
  --actor rigorous-auditor \
  --database "$COMPLIANCE_DB" | tee "$WORK/compliance_ingest.json"
"$PYTHON" -m compliance_log.cli ingest \
  --snapshot docs/demo_snapshot.json \
  --outcome '{"status":"approved","ref":"rigorous-002"}' \
  --actor rigorous-auditor \
  --database "$COMPLIANCE_DB" | tee "$WORK/compliance_ingest2.json"

CHAIN=$("$PYTHON" -m compliance_log.cli verify-chain --database "$COMPLIANCE_DB")
echo "$CHAIN"
echo "$CHAIN" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('chain_ok') and d.get('genesis_ok') else 1)"
pass "Hash chain + genesis verified"

section "Compliance Logger — F1–F9 institutional check"
CHECK=$("$PYTHON" -m compliance_log.cli check --database "$COMPLIANCE_DB")
echo "$CHECK"
echo "$CHECK" | "$PYTHON" -c "
import sys, json
r = json.load(sys.stdin)
failed = [c for c in r.get('checks', []) if not c.get('passed')]
if not r.get('passed'):
    print('FAILED gates:', failed, file=sys.stderr)
    sys.exit(1)
print('All gates passed:', [c['name'] for c in r.get('checks', [])])
"
pass "Institutional F1–F9 check"

section "Compliance Logger — export + F9 repro"
EXPORT=$("$PYTHON" -m compliance_log.cli export \
  --database "$COMPLIANCE_DB" \
  --out-dir "$WORK/compliance_bundle" \
  --tarball "$COMPLIANCE_TAR")
echo "$EXPORT"
echo "$EXPORT" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('ok') and d.get('bundle_sha256') else 1)"
test -f "$COMPLIANCE_TAR"
test -f "${COMPLIANCE_TAR}.sha256"
test -f "${COMPLIANCE_TAR}.sha256.json"
pass "Audit bundle + SHA256 sidecar"

REPRO=$("$PYTHON" -m compliance_log.cli export --database "$COMPLIANCE_DB" --repro-check)
echo "$REPRO"
echo "$REPRO" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('ok') else 1)"
pass "F9 reproducibility"

section "Compliance Logger — offline verify-bundle (auditor dry-run)"
VERIFY=$("$PYTHON" -m compliance_log.cli verify-bundle --tarball "$COMPLIANCE_TAR")
echo "$VERIFY"
echo "$VERIFY" | "$PYTHON" -c "
import sys, json
d = json.load(sys.stdin)
required = ['ok','genesis_ok','chain_ok','lamport_ok','bundle_sha256_ok','institutional_passed']
if not all(d.get(k) for k in required):
    print('verify-bundle incomplete:', d, file=sys.stderr)
    sys.exit(1)
"
pass "Offline auditor verify-bundle"

section "Compliance Logger — negative gate (genesis-only abort)"
GENESIS_ONLY="$WORK/genesis_only.sqlite"
"$PYTHON" - <<PY
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.export import build_audit_bundle
db = "$GENESIS_ONLY"
AppendOnlyLedger(db)
result = build_audit_bundle(db, out_dir="$WORK/genesis_out", tarball_path="$WORK/genesis_out.tar")
assert not result.ok, "expected institutional abort"
assert not result.institutional_passed
print({"ok": result.ok, "institutional_passed": result.institutional_passed})
PY
pass "Export correctly aborts on genesis-only ledger"

section "Compliance Logger — tampered genesis detection"
TAMPER_DB="$WORK/tamper.sqlite"
"$PYTHON" - <<PY
from pathlib import Path
from inst_spine.ledger import AppendOnlyLedger
from inst_spine.export import validate_before_export, verify_audit_bundle, build_audit_bundle
from compliance_log.ingest import log_decision

db = Path("$TAMPER_DB")
log_decision(snapshot={"x":1}, outcome={"ok":True}, actor="t", database=db)
ledger = AppendOnlyLedger(db)
ledger.anchor_path.write_text('{"instance_uuid":"fake","genesis_hash":"dead","config_hash":"bad"}', encoding="utf-8")
v = validate_before_export(ledger=ledger)
assert not v.ok, "tampered anchor should fail validation"
result = build_audit_bundle(db, out_dir="$WORK/tamper_out", tarball_path="$WORK/tamper_out.tar")
assert not result.ok
print({"validation_ok": v.ok, "export_ok": result.ok, "message": v.message})
PY
pass "Tampered genesis anchor rejected"

section "Proxy-Risk — shadow evaluate + ledger"
SHADOW=$("$PYTHON" -m proxy_risk.cli evaluate \
  --client-id rigorous-broker \
  --method POST \
  --path /orders \
  --body '{"symbol":"AAPL","qty":100}' \
  --idempotency-key rigorous-shadow-1 \
  --database "$PROXY_DB")
echo "$SHADOW"
echo "$SHADOW" | parse_json_objects | "$PYTHON" -c "
import sys, json
objs = json.load(sys.stdin)
resp = objs[0]
verify = objs[1] if len(objs) > 1 else {}
assert resp.get('decision') == 'approve', resp
assert verify.get('chain_ok'), verify
"
pass "Shadow evaluate + ledger chain"

section "Proxy-Risk — idempotency duplicate rejection (in-process session)"
"$PYTHON" - <<'PY'
import asyncio
import json
from inst_spine.rates import MemoryIdempotencyBackend
from proxy_risk.router import GateDecision, ProxyRequest, ProxyRiskGateway

async def main():
    gw = ProxyRiskGateway(shadow_mode=True, idempotency=MemoryIdempotencyBackend())
    req = ProxyRequest(
        client_id="rigorous-broker",
        method="POST",
        path="/orders",
        body={"symbol": "AAPL", "qty": 100},
        idempotency_key="rigorous-shadow-1",
    )
    r1 = await gw.evaluate(req)
    r2 = await gw.evaluate(req)
    assert r1.decision == GateDecision.APPROVE, r1
    assert r2.decision == GateDecision.REJECT, r2
    print(json.dumps({"first": r1.decision.value, "duplicate": r2.decision.value, "reason": r2.reason}))

asyncio.run(main())
PY
pass "Duplicate idempotency key rejected"

section "Proxy-Risk — Z-score circuit kill (in-process session)"
"$PYTHON" - <<'PY'
import asyncio
import json
from inst_spine.rates import ZScoreDriftDetector
from proxy_risk.router import GateDecision, ProxyRequest, ProxyRiskGateway

async def main():
    drift = ZScoreDriftDetector(window=5, z_max=2.0)
    for p in [10.0, 10.1, 9.9, 10.0, 10.2]:
        drift.update(p)
    gw = ProxyRiskGateway(drift=drift, shadow_mode=True)
    resp = await gw.evaluate(
        ProxyRequest(client_id="c", method="POST", path="/x", body={}, reference_price=50.0)
    )
    assert resp.decision == GateDecision.KILL, resp
    print(json.dumps({"decision": resp.decision.value, "reason": resp.reason}))

asyncio.run(main())
PY
pass "Z-score drift triggers circuit kill"

section "Proxy-Risk — env circuit kill (CLI)"
KILL_ENV=$(INST_CIRCUIT_KILL=1 "$PYTHON" -m proxy_risk.cli evaluate \
  --client-id rigorous-broker \
  --method POST \
  --path /env-kill \
  --body '{}' \
  --idempotency-key rigorous-env-kill-1 \
  --database "$PROXY_DB" 2>&1 || true)
echo "$KILL_ENV"
echo "$KILL_ENV" | parse_json_objects | "$PYTHON" -c "
import sys, json
resp = json.load(sys.stdin)[0]
assert resp.get('decision') == 'kill', resp
"
pass "INST_CIRCUIT_KILL env severs traffic"

section "Proxy-Risk — live upstream forward (httpbin)"
export PROXY_RISK_UPSTREAM_BASE="https://httpbin.org"
LIVE=$("$PYTHON" -m proxy_risk.cli evaluate \
  --live \
  --client-id rigorous-broker \
  --method POST \
  --path /post \
  --body '{"rigorous":"live-forward"}' \
  --idempotency-key rigorous-live-1 \
  --database "$PROXY_DB")
echo "$LIVE"
echo "$LIVE" | parse_json_objects | "$PYTHON" -c "
import sys, json
resp = json.load(sys.stdin)[0]
assert resp.get('decision') == 'approve', resp
assert resp.get('upstream_status') == 200, resp
body = resp.get('upstream_body') or {}
assert body.get('json', {}).get('rigorous') == 'live-forward', body
"
pass "Live upstream forward to httpbin.org/post"

section "Proxy-Risk — log-before-forward WAL evidence"
"$PYTHON" - <<PY
import json
from inst_spine.ledger import AppendOnlyLedger
ledger = AppendOnlyLedger("$PROXY_DB")
rows = [e for e in ledger.list_entries() if e.get("event_type") == "proxy_request"]
details = [str((e.get("payload") or {}).get("detail", "")) for e in rows]
assert any("forward pending" in d for d in details), details
assert any("forwarded" in d for d in details), details
print(json.dumps({"proxy_rows": len(rows), "details": details}, indent=2))
PY
pass "Log-before-forward + post-forward ledger entries present"

section "Proxy-Risk — institutional check + export"
PROXY_CHECK=$("$PYTHON" -m proxy_risk.cli check --database "$PROXY_DB")
echo "$PROXY_CHECK"
echo "$PROXY_CHECK" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('passed') else 1)"

PROXY_EXPORT=$("$PYTHON" -m proxy_risk.cli export \
  --database "$PROXY_DB" \
  --out-dir "$WORK/proxy_bundle" \
  --tarball "$PROXY_TAR")
echo "$PROXY_EXPORT"
echo "$PROXY_EXPORT" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('ok') else 1)"

PROXY_VERIFY=$("$PYTHON" -m compliance_log.cli verify-bundle --tarball "$PROXY_TAR")
echo "$PROXY_VERIFY"
echo "$PROXY_VERIFY" | "$PYTHON" -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d.get('ok') else 1)"
pass "Proxy institutional check + export + offline verify"

section "Proxy-Risk — p99 shadow latency bench"
"$PYTHON" - <<'PY'
import asyncio
import json
import time
from inst_spine.rates import MemoryIdempotencyBackend, MemoryTokenBucketBackend, TokenBucket
from proxy_risk.router import ProxyRequest, ProxyRiskGateway

async def bench():
    backend = MemoryTokenBucketBackend()
    bucket = TokenBucket(capacity=100_000.0, refill_rate=100_000.0, key="rigorous-bench", backend=backend)
    gw = ProxyRiskGateway(shadow_mode=True, bucket=bucket, idempotency=MemoryIdempotencyBackend())
    latencies = []
    for i in range(10_000):
        t0 = time.perf_counter()
        await gw.evaluate(ProxyRequest(client_id="bench", method="POST", path=f"/o/{i}", body={"i": i}))
        latencies.append((time.perf_counter() - t0) * 1000.0)
    latencies.sort()
    p50 = latencies[int(len(latencies) * 0.50) - 1]
    p99 = latencies[int(len(latencies) * 0.99) - 1]
    p999 = latencies[int(len(latencies) * 0.999) - 1]
    result = {"iterations": len(latencies), "p50_ms": round(p50, 4), "p99_ms": round(p99, 4), "p999_ms": round(p999, 4)}
    print(json.dumps(result, indent=2))
    assert p99 < 10.0, f"p99 {p99:.3f}ms exceeds 10ms target"

asyncio.run(bench())
PY
pass "p99 shadow latency < 10ms (10k iterations)"

section "Summary"
echo ""
echo "================================================================"
echo "ALL RIGOROUS TESTS PASSED"
echo "Finished: $(date -u +%Y-%m-%dT%H:%M:%SZ) UTC"
echo "Log: $LOG_FILE"
echo "================================================================"

ln -sf "$(basename "$LOG_FILE")" "$LATEST_LINK"
echo "Latest symlink: $LATEST_LINK -> $(basename "$LOG_FILE")"
