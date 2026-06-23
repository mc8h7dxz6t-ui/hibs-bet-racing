# Proxy-Risk Gateway — Sales & Technical Specification

**Product:** Proxy-Risk Gateway (#2)  
**SKU:** `proxy-risk`  
**Version:** Gold standard (full institutional test suite, live httpx forward, workflow UI)  
**Audience:** Fintech ops, quant infra, platform engineering, procurement, auditors

---

## Executive summary

**One job:** Institutional **outbound API firewall** — rate limit, dedupe, statistical kill switch, and **cryptographic audit** before traffic hits upstream brokers, payment rails, or core APIs.

**One-line pitch:** *Control what leaves your boundary — and prove every gate decision.*

| | |
|---|---|
| **Price band** | £400–£1,200/mo per tenant |
| **Default mode** | Shadow (gates run, no upstream call) |
| **Live mode** | Sync WAL → forward → fail-closed on 4xx/5xx |
| **Proof** | Every approve/reject/kill logged to genesis chain |

---

## Problem → solution

| Buyer pain | Industry default | Proxy-Risk |
|------------|------------------|------------|
| Runaway API after bug | Rate limit only | Bucket + Z-score + circuit kill |
| Double-submit billing | Best-effort dedupe | Idempotency CAS (Redis or memory) |
| No proxy audit trail | Access logs (mutable) | Genesis-anchored ledger per outcome |
| Fear of going live | All-or-nothing | Shadow burn-in → `--live` when ready |
| Upstream errors as success | Optimistic forward | 4xx/5xx → REJECT (fail-closed) |

---

## Ideal buyer

| Segment | Use case | Why us |
|---------|----------|--------|
| **Broker / fintech ops** | Order routing guardrails | Shadow default + live forward |
| **Quant / trading infra** | Fat-finger protection | Z-score drift on reference price |
| **Platform teams** | Outbound API governance | Full gate chain + export |
| **Payments** | Idempotent payout proxy | Dedupe + audit bundle |

**Win when:** buyer needs **fail-closed outbound control + proof**.  
**Lose when:** buyer needs sub-5ms RTB exchange insert (Go/Rust territory) or full API lifecycle (Kong/Apigee).

---

## Competitive positioning

| Capability | API gateway (Kong, Apigee) | WAF / rate limit SaaS | **Proxy-Risk** |
|------------|---------------------------|------------------------|----------------|
| Rate limiting | Yes | Yes | **Token bucket + Redis atomic** |
| Kill switch | Rare | Sometimes | **Circuit + Z-score drift** |
| Shadow mode | No | No | **Default — burn-in without capital risk** |
| Idempotency | Plugin | Varies | **First-class CAS backend** |
| Audit per gate outcome | Access log | Metrics | **Genesis chain — every decision** |
| Offline verify | No | No | **`verify-bundle`** |
| Air-gap deploy | Rare | SaaS | **Yes** |

---

## Architecture

```
Client / automation
        │
        ▼
┌─────────────────────────────────────────────┐
│  HOT PATH (in-memory / Redis)               │
│  circuit → schema → bucket → idempotency    │
│         → z-score drift                     │
└─────────┬───────────────────────────────────┘
          │
    ┌─────┴─────┐
    ▼           ▼
 SHADOW       LIVE (httpx)
 (no upstream)  sync WAL → forward → fail-closed
    │           │
    └─────┬─────┘
          ▼
┌───────────────────┐
│  AppendOnlyLedger │  every APPROVE / REJECT / KILL
│  (inst_spine)     │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  export + verify  │  same spine as Compliance Logger
└───────────────────┘
```

### Gate chain (order matters)

```
1. circuit      — INST_CIRCUIT_KILL emergency sever
2. schema       — required fields + allowed HTTP methods
3. token bucket — per-client rate (memory or Redis)
4. idempotency  — duplicate key → REJECT
5. z-score      — reference_price drift → KILL
6. forward      — shadow skip | live httpx to upstream
```

### Latency

| Mode | Target | Notes |
|------|--------|-------|
| Shadow | p99 < 10ms | In-memory gates; async ledger write |
| Live | upstream RTT + gates | WAL sync before forward |
| Multi-instance | Redis backends | Token bucket + idempotency CAS |

**Honest non-goal:** sub-5ms RTB pre-bid — use Go/Rust exchange adapters.

### Package layout (standalone extract)

```
proxy-risk/
├── src/proxy_risk/         # router + CLI (2 modules)
├── src/inst_spine/         # shared audit spine (required)
├── docs/demo_proxy_request.json
├── scripts/demo_proxy_risk.sh
└── pyproject.toml          # proxy-risk entry point
```

**Zero dependency** on `compliance_log`, sports, or racing code.

---

## CLI reference

```bash
pip install -e ".[dev,instpp]"
```

| Command | Purpose |
|---------|---------|
| `proxy-risk evaluate [--live] --client-id ID --path PATH --body JSON` | Single request through gate chain |
| `proxy-risk check [--database PATH]` | F1–F9 on proxy ledger |
| `proxy-risk export [--database PATH] [--tarball PATH]` | Audit bundle |
| `proxy-risk verify-bundle --tarball PATH` | Offline auditor replay |
| `proxy-risk serve [--port PORT]` | HTTP gateway endpoint |

### Request contract

```json
{
  "client_id": "broker-demo",
  "method": "POST",
  "path": "/v1/orders",
  "body": {
    "symbol": "AAPL",
    "qty": 100,
    "side": "buy"
  },
  "reference_price": 10.5,
  "idempotency_key": "order-2026-001"
}
```

### Gate outcomes

| Decision | Meaning |
|----------|---------|
| `approve` | Passed all gates; forwarded (live) or shadow-OK |
| `reject` | Schema, bucket, idempotency, or upstream 4xx/5xx |
| `kill` | Circuit open or Z-score drift breach |

---

## Environment variables

| Variable | Purpose |
|----------|---------|
| `PROXY_RISK_UPSTREAM_BASE` | Live upstream URL (required for `--live`) |
| `PROXY_RISK_UPSTREAM_TOKEN` | Bearer token for upstream |
| `PROXY_RISK_API_TOKEN` | Optional auth on `/evaluate` serve |
| `INST_CIRCUIT_KILL=1` | Emergency traffic sever |
| `INST_REDIS_URL` | Multi-instance idempotency + token bucket |
| `INST_PROXY_SHADOW` | Default shadow mode for workflow UI |

**Fail-closed:** Redis backend outage → reject (not bypass).

---

## Workflow UI (single-product console)

```bash
inst-workflow serve --product proxy --port 8790
# → http://127.0.0.1:8790
```

5-step guided workflow: **Shadow → Live forward → F1–F9 → Export → Verify offline**

Env alternative: `INST_WORKFLOW_PRODUCT=proxy`

---

## HTTP serve mode

```bash
export PROXY_RISK_UPSTREAM_BASE=https://api.broker.example.com
proxy-risk serve --port 18443
```

- JSON body validation  
- Optional bearer auth (`PROXY_RISK_API_TOKEN`)  
- Shadow by default; `live: true` in payload for forward  

---

## Export artifacts

Same deterministic bundle format as Compliance Logger (`product: proxy-risk` in MANIFEST).

```bash
proxy-risk export --database data/proxy.sqlite --tarball proxy_bundle.tar
proxy-risk verify-bundle --tarball proxy_bundle.tar
```

---

## Security & deployment

| Concern | Approach |
|---------|----------|
| **Credential storage** | Env token adapter (Vault swap documented) |
| **Upstream trust** | Fail-closed on HTTP errors |
| **Emergency stop** | `INST_CIRCUIT_KILL=1` |
| **Audit** | Every gate outcome in ledger |
| **Multi-instance** | Redis for shared rate/idempotency state |

### Reference deploy

1. **Week 1–2:** Shadow mode — all clients, no upstream  
2. **Week 3:** Export + auditor verify-bundle  
3. **Go-live:** `--live` per client_id whitelist  
4. **Ongoing:** Nightly export to cold storage  

---

## Proof & diligence

```bash
./scripts/demo_proxy_risk.sh
SKIP_LIVE=1 ./scripts/demo_proxy_risk.sh   # air-gapped
proxy-risk verify-bundle --tarball data/demo/proxy_bundle.tar
```

| Artifact | Path |
|----------|------|
| Rigorous test log | `docs/test_logs/instpp_rigorous_latest.log` |
| Buyer one-pager | `docs/PROXY_RISK_BUYER.md` |
| Deep dive | `docs/INST_PLUS_DEEP_DIVE_COMPLIANCE_PROXY.md` |
| Architecture | `src/proxy_risk/README.md` |

---

## Non-goals (say no in RFPs)

- **Not** sub-5ms RTB exchange insert
- **Not** DoubleVerify / IAS pre-bid placement verification
- **Not** HashiCorp Vault in P1 (env adapter; swap documented)
- **Not** inbound webhook mesh (see Product #5 Webhook Mesh)
- **Not** full API lifecycle / developer portal (Kong/Apigee territory)

---

## Pricing & packaging

| Tier | Band | Includes |
|------|------|----------|
| **Tenant license** | £400–£1,200/mo | Gate chain + ledger + export |
| **Workflow console** | Included | `inst-workflow serve --product proxy` |
| **Redis HA add-on** | +£100–200/mo | Multi-instance bucket + idempotency |
| **Implementation** | Custom SOW | Upstream mapping, shadow burn-in, kill thresholds |

**Sell separately** from Compliance Logger — different buyer, different diligence.

---

## RFP quick answers

| Question | Answer |
|----------|--------|
| Outbound rate limit + kill switch? | **Yes** |
| Shadow burn-in before live? | **Yes** — default |
| Idempotency / double-billing protection? | **Yes** |
| Audit trail per gate decision? | **Yes** — all outcomes logged |
| Sub-ms RTB pre-bid? | **No** |
| Inbound webhook dedupe? | **No** — Webhook Mesh (#5) |

---

## Related documents

- `docs/PROXY_RISK_BUYER.md` — one-page buyer sheet  
- `docs/PORTFOLIO_SALES_SHEET.md` — portfolio pricing matrix  
- `docs/BUYER_EVIDENCE_PACK.md` — procurement dry-run  
- `docs/INST_PLUS_PRE_REV_VALUATION.md` — IP valuation framework  
- `docs/DEMO.md` — demo commands
