# Webhook Idempotency Mesh — Buyer Sheet

**One job:** Inbound webhooks → signature verify → idempotency CAS → WAL fsync → HTTP 200 → async forward — never double-process a billing event.

**Pitch:** *Ack webhooks only after durability — with cryptographic proof you never charged twice.*

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| Fintech / SaaS billing | Double webhook delivery charges twice | Redis SETNX idempotency + WAL before ack |
| Platform teams | Custom middleware without audit trail | Genesis ledger cold path + `verify-bundle` |
| Multi-instance deploy | In-memory dedupe fails across pods | Redis fail-closed idempotency |

**Price band:** £199–£599/mo per tenant.

---

## Tech edge (proof)

| Capability | Evidence |
|------------|----------|
| WAL before ack | `INST_WAL_PATH` fsync before HTTP 200 |
| HMAC fail-closed | Invalid signature → 401 |
| Stripe route | `/v1/ingress/stripe/{client_id}` header mapping |
| Offline proof | `export` + `verify-bundle` on ingress ledger |
| Replay capture | `WEBHOOK_REPLAY_CAPTURE_DIR` → byte-identical `.wrcap` |

**Auditor dry-run:**
```bash
export WEBHOOK_PROVIDER_SECRET=demo-secret
./scripts/demo_webhook_mesh.sh
webhook-mesh verify-bundle --tarball ./webhook_mesh_bundle.tar
```

---

## 60-second demo

```bash
export WEBHOOK_PROVIDER_SECRET=demo-secret
./scripts/demo_webhook_mesh.sh
```

---

## Non-goals

- Not a full event bus (Kafka, SNS)
- Not Stripe Connect dashboard
- Background queue without Redis Stream: tasks lost on crash (documented)

---

## CLI

| Command | Purpose |
|---------|---------|
| `serve` | HTTP ingress gateway |
| `demo-sign` | Generate HMAC for test payloads |
| `check` | F1–F9 on ingress ledger |
| `export` | Audit bundle |
| `verify-bundle` | Offline auditor replay |

See `src/webhook_mesh/README.md` for architecture.  
**Full spec:** `docs/WEBHOOK_MESH_SALES_TECH_SPEC.md`

---

## Next step

| Step | Action |
|------|--------|
| 1 | `export WEBHOOK_PROVIDER_SECRET=demo-secret && ./scripts/demo_webhook_mesh.sh` |
| 2 | `webhook-mesh verify-bundle --tarball ./webhook_mesh_bundle.tar` |
| 3 | RFP depth → `docs/WEBHOOK_MESH_SALES_TECH_SPEC.md` |
| 4 | Portfolio pricing → `docs/PORTFOLIO_SALES_SHEET.md` |
