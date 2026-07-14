# Webhook Idempotency Mesh — Sales & Technical Specification

**Product:** Webhook Idempotency Mesh (#5)  
**SKU:** `webhook-mesh`  
**Version:** Gold standard (Stripe + Shopify routes, WAL-before-ack, genesis ledger)  
**Audience:** SaaS billing, fintech platform teams, procurement, auditors

---

## Executive summary

**One job:** Inbound webhooks → signature verify → idempotency CAS → **WAL fsync** → HTTP 200 → async forward — **never double-process a billing event**.

**One-line pitch:** *Ack webhooks only after durability — with cryptographic proof you never charged twice.*

| | |
|---|---|
| **Deploy** | VPC + Redis (multi-instance) + SQLite genesis ledger |
| **Proof** | WAL before ack + ingress ledger + `verify-bundle` |
| **Demo** | 60 seconds CLI · Stripe/Shopify signature demo |

---

## Problem → solution

| Buyer pain | Industry default | Webhook Mesh |
|------------|------------------|--------------|
| Double webhook → double charge | Best-effort dedupe | **Redis SETNX + WAL before 200** |
| Custom middleware, no audit | App logs (mutable) | **Genesis ledger + export** |
| Multi-instance dedupe fails | In-memory only | **Redis fail-closed idempotency** |
| Invalid signature accepted | Soft fail | **HMAC fail-closed → 401** |
| Auditor distrust | “Trust our dashboard” | **Offline `verify-bundle`** |

---

## Ideal buyer

| Segment | Use case | Why us |
|---------|----------|--------|
| **SaaS billing** | Stripe/Shopify webhook ingress | Native routes + signature verify |
| **Fintech** | Payment event dedupe | WAL-before-ack durability model |
| **Platform teams** | Multi-pod webhook handling | Redis CAS across instances |

**Win when:** buyer needs **idempotent ingress + audit proof**, not a full event bus.  
**Lose when:** buyer needs Kafka-scale streaming or Stripe Connect dashboard.

---

## Competitive positioning

| Capability | Stripe idempotency | Custom middleware | **Webhook Mesh** |
|------------|-------------------|-------------------|------------------|
| WAL before provider ack | No | Rare | **Yes** |
| Redis SETNX multi-instance | Stripe-only | DIY | **inst_spine Lua CAS** |
| Stripe / Shopify routes | Stripe-native | DIY | **Built-in `/v1/ingress/stripe|shopify/{tenant}`** |
| Genesis audit export | No | No | **ledger + verify-bundle** |
| Fail-closed on Redis error | N/A | Varies | **Yes (idempotency)** |

---

## Architecture

```
POST /v1/ingress/{tenant}
  OR /v1/ingress/stripe/{tenant}
  OR /v1/ingress/shopify/{tenant}
  → HMAC verify (fail-closed)
  → Redis idempotency CAS
  → WAL fsync
  → HTTP 200 OK
  → async forward + retry → DLQ
  → cold path: genesis ledger append
```

### Provider routes

| Route | Signature |
|-------|-----------|
| `/v1/ingress/stripe/{client_id}` | Stripe-Signature header |
| `/v1/ingress/shopify/{client_id}` | X-Shopify-Hmac-Sha256 |
| `/v1/ingress/{client_id}` | Generic HMAC (`WEBHOOK_PROVIDER_SECRET`) |

```bash
webhook-mesh demo-sign --provider stripe --body '{"id":"evt_123"}'
webhook-mesh demo-sign --provider shopify --body '{"order":1}'
```

---

## CLI reference

```bash
pip install -e ".[dev,instpp]"
export WEBHOOK_PROVIDER_SECRET=demo-secret
```

| Command | Purpose |
|---------|---------|
| `webhook-mesh serve [--port PORT]` | HTTP ingress gateway |
| `webhook-mesh demo-sign [--provider generic\|stripe\|shopify]` | Generate test signatures |
| `webhook-mesh check [--database PATH]` | F1–F9 on ingress ledger |
| `webhook-mesh export [--database PATH] [--tarball PATH]` | Audit bundle |
| `webhook-mesh verify-bundle --tarball PATH` | Offline auditor replay |

---

## Proof & diligence

```bash
export WEBHOOK_PROVIDER_SECRET=demo-secret
./scripts/demo_webhook_mesh.sh
./scripts/instpp_rigorous_test.sh
webhook-mesh verify-bundle --tarball ./webhook_mesh_bundle.tar
```

| Artifact | Path |
|----------|------|
| Rigorous test log | `docs/test_logs/instpp_rigorous_latest.log` |
| Buyer one-pager | `docs/WEBHOOK_MESH_BUYER.md` |
| Architecture | `src/webhook_mesh/README.md` |

---

## Honest limits

- Background queue: tasks lost on crash if not Redis Stream (documented — buyer configures Stream for production)
- Not a full event bus (Kafka, SNS, EventBridge)

---

## Non-goals (say no in RFPs)

- Not a full event bus (Kafka, SNS)
- Not Stripe Connect dashboard or billing UI
- Not guaranteed at-least-once forward without Redis Stream config

---


## RFP quick answers

| Question | Answer |
|----------|--------|
| Prevent double webhook processing? | **Yes** — SETNX + WAL before 200 |
| Stripe signature verify? | **Yes** — dedicated route |
| Shopify HMAC verify? | **Yes** — dedicated route |
| Multi-instance dedupe? | **Yes** — Redis fail-closed |
| Offline third-party verification? | **Yes** — `verify-bundle` |
| Full event streaming platform? | **No** |

---

## Related documents

- `docs/WEBHOOK_MESH_BUYER.md` — one-page buyer sheet  
- `docs/BUYER_EVIDENCE_PACK.md` — procurement dry-run
