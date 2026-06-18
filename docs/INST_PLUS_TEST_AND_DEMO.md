# Inst++ — Test & Advertise Playbook

**Purpose:** Copy-paste commands to prove, demo, and sell Inst++ products. Run `scripts/instpp_smoke_test.sh` before any external demo.

---

## Quick install

```bash
pip install -e ".[dev,instpp]"
chmod +x scripts/instpp_smoke_test.sh scripts/export_*.sh
./scripts/instpp_smoke_test.sh
```

---

## Product readiness matrix

| # | Product | Advertise-ready | Demo command |
|---|---------|-----------------|--------------|
| 1 | Compliance Logger | **Yes** (P2 export) | `compliance-log export --repro-check` |
| 2 | Proxy-Risk Gateway | **Yes** (shadow) | `proxy-risk evaluate --reference-price 50` |
| 3 | Alt-Data Extractor | Demo only | `altdata poll --url …` |
| 4 | AI Kit | Demo only | `ai-kit run --max-tokens 1000` |
| 5 | Webhook Mesh | **Yes** (P1) | `webhook-mesh serve` |
| 6 | Ad Guard | **Yes** (P1) | `ad-guard serve` |
| 7 | Health Telemetry | Not started | — |

**Sell now:** Products **1, 2, 5, 6**. Position **3, 4** as pilots. Do not advertise **7** without a buyer.

---

### Institutional stack (enterprise buyers)

| Layer | Incumbent | Inst++ |
|-------|-----------|--------|
| Pre-bid (DV/IAS) | Placement + fraud | **Complement** — don't compete |
| GenAI (NeMo/Bedrock) | Creative safety | **Downstream** — spend after approval |
| Compliance audit | CSV / GRC | **#1 Compliance Logger** |
| Marketing API spend | Scripts / alerts | **#6 Ad Guard** |
| Webhook billing | Custom code | **#5 Webhook Mesh** |

Full map: `docs/INSTITUTIONAL_ENTERPRISE_STACK.md`

---

## Product 5 — Webhook Idempotency Mesh

### Start server

```bash
export WEBHOOK_PROVIDER_SECRET=whsec_demo_secret
export WEBHOOK_DISPATCH_MODE=background   # dev; use redis + INST_REDIS_URL in prod
webhook-mesh serve --port 8787 --wal ./data/demo_webhook.wal
```

### Sign + send test webhook

```bash
echo '{"event":"payment.succeeded","id":"evt_demo_1"}' > /tmp/payload.json

webhook-mesh demo-sign --secret whsec_demo_secret --body-file /tmp/payload.json

SIG=$(webhook-mesh demo-sign --secret whsec_demo_secret --body-file /tmp/payload.json | python3 -c "import sys,json; print(json.load(sys.stdin)['signature'])")

curl -s -X POST "http://127.0.0.1:8787/v1/ingress/demo-tenant" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Id: evt_demo_1" \
  -H "X-Target-Forward-Url: https://httpbin.org/post" \
  -H "X-Provider-Signature: $SIG" \
  --data-binary @/tmp/payload.json | jq .

# Duplicate — returns 200 ALREADY_PROCESSED (Stripe-safe)
curl -s -X POST "http://127.0.0.1:8787/v1/ingress/demo-tenant" \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Id: evt_demo_1" \
  -H "X-Target-Forward-Url: https://httpbin.org/post" \
  -H "X-Provider-Signature: $SIG" \
  --data-binary @/tmp/payload.json | jq .
```

### Export audit bundle

```bash
./scripts/export_webhook_audit.sh ./data/demo_webhook.wal ./webhook_audit.tar
```

### Production env vars

| Variable | Purpose |
|----------|---------|
| `WEBHOOK_PROVIDER_SECRET` | HMAC secret (required) |
| `INST_REDIS_URL` | Idempotency CAS + durable delivery queue |
| `WEBHOOK_DISPATCH_MODE` | `redis` (prod) or `background` (dev) |
| `INST_WAL_PATH` | Sync fsync WAL path |

---

## Product 6 — Ad-Tech Budget Guardrail

### Start server (shadow mode — default)

```bash
ad-guard serve --port 8788 --database ./data/demo_ad_guard.sqlite
```

### Approve normal spend

```bash
curl -s -X POST "http://127.0.0.1:8788/v1/guard/agency-1" \
  -H "Content-Type: application/json" \
  -H "X-Ad-Provider: google" \
  -d '{"campaignId":"12345","bidMicros":2500000}' | jq .
```

### Trigger spend anomaly (after baseline warms up)

```bash
for i in $(seq 1 6); do
  curl -s -X POST "http://127.0.0.1:8788/v1/guard/agency-1" \
    -H "Content-Type: application/json" \
    -d "{\"campaign_id\":\"c1\",\"spend_delta\":10.$i}" > /dev/null
done
curl -s -X POST "http://127.0.0.1:8788/v1/guard/agency-1" \
  -H "Content-Type: application/json" \
  -d '{"campaign_id":"c1","spend_delta":9999}' | jq .
```

### Export cryptographic audit bundle

```bash
ad-guard export --database ./data/demo_ad_guard.sqlite --repro-check
./scripts/export_ad_audit.sh ./data/demo_ad_guard.sqlite ./ad_audit ./ad_audit.tar
```

### Institutional positioning (sales copy)

> Inst++ Ad Guard is the **Compliance & Spend Control** layer between approved creative and marketing APIs. It does **not** replace DoubleVerify/IAS pre-bid or NeMo/Bedrock GenAI safety — it guards **dollars leaving the account** with a genesis-anchored audit trail.

See `docs/AD_GUARD_INSTITUTIONAL_STACK.md`.

---

## Product 1 — Compliance Logger (anchor product)

```bash
compliance-log ingest --snapshot /tmp/snapshot.json --actor demo --database ./data/demo_compliance.sqlite
compliance-log verify-chain --database ./data/demo_compliance.sqlite
compliance-log export --database ./data/demo_compliance.sqlite --repro-check
```

---

## Product 2 — Proxy-Risk Gateway

```bash
proxy-risk evaluate \
  --client-id broker-1 \
  --reference-price 10.5 \
  --body '{"symbol":"AAPL","qty":100}' \
  --database ./data/demo_proxy.sqlite
```

---

## Advertise checklist (before listing or outreach)

- [ ] `./scripts/instpp_smoke_test.sh` passes
- [ ] Demo video or screenshot of `curl` → `ACCEPTED` / `approve`
- [ ] Export bundle + SHA256 sidecar generated
- [ ] Pricing line ready (£199–£599/mo webhook; £300–£800/mo ad guard)
- [ ] Non-goals stated (no RTB insert, no LLM firewall, no sports)
- [ ] Separate listing per product — not one mega-bundle

---

## What is NOT 100% (honest limits)

| Gap | Impact on advertise |
|-----|---------------------|
| Sub-5ms RTB exchange insert | Say no on RTB RFPs — no harm to API proxy buyers |
| Multi-tenant SaaS UI | Not needed for first £2k MRR |
| Proxy-Risk live upstream forward | Shadow demo OK; say "shadow" in listing |
| Health Telemetry (#7) | Do not list |

---

## Related docs

- `docs/INST_PLUS_STRATEGY.md` — portfolio strategy
- `docs/AD_GUARD_INSTITUTIONAL_STACK.md` — enterprise positioning
- `docs/NEW_PRODUCT_INST_PLUS_ROADMAPS.md` — technical roadmaps
