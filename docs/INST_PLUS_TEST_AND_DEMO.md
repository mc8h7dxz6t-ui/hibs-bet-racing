# Inst++ — Test & Advertise Playbook

**Purpose:** Copy-paste commands to prove, demo, and sell Inst++ products. Run `scripts/instpp_smoke_test.sh` before any external demo.

---

## Quick install

```bash
pip install -e ".[dev,instpp]"
chmod +x scripts/demo_instpp.sh scripts/demo_*.sh scripts/instpp_*.sh scripts/export_*.sh
./scripts/demo_instpp.sh
```

See **`docs/DEMO.md`** for the full buyer demo guide.

### Rigorous E2E (Compliance + Proxy-Risk)

Full integration test with timestamped log:

```bash
./scripts/instpp_rigorous_test.sh
# Log: docs/test_logs/instpp_rigorous_<timestamp>.log
# Latest: docs/test_logs/instpp_rigorous_latest.log
```

---

## Product readiness matrix

| # | Product | Advertise-ready | Demo command |
|---|---------|-----------------|--------------|
| 1 | Compliance Logger | **Yes** (gold standard) | `./scripts/demo_instpp.sh` |
| 2 | Proxy-Risk Gateway | **Yes** (gold standard) | `./scripts/demo_instpp.sh` |
| 3 | Alt-Data Extractor | **P1+** | `altdata poll --ctx '{...}'` · `./scripts/demo_altdata.sh` |
| 4 | AI Kit | **P1+** | `ai-kit run --steps 3` · `./scripts/demo_ai_kit.sh` |
| 5 | Webhook Mesh | **P1+** | `webhook-mesh serve` · `./scripts/demo_webhook_mesh.sh` |
| 6 | Ad Guard | **P1+** | `ad-guard evaluate` · `./scripts/demo_ad_guard.sh` |
| 7 | Health Telemetry | **Scaffold** | `health-telemetry ingest` · `./scripts/demo_health_telemetry.sh` |
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

## Product 1 & 2 — One-command demo (recommended)

```bash
./scripts/demo_instpp.sh
# Artifacts → data/demo/compliance_bundle.tar + data/demo/proxy_bundle.tar
```

Individual products: `./scripts/demo_compliance_logger.sh` · `./scripts/demo_proxy_risk.sh`

---

## Product 1 — Compliance Logger (manual steps)

```bash
compliance-log ingest --snapshot docs/demo_snapshot.json --actor demo --database ./data/demo_compliance.sqlite
compliance-log verify-chain --database ./data/demo_compliance.sqlite
compliance-log check --database ./data/demo_compliance.sqlite
compliance-log export --database ./data/demo_compliance.sqlite --repro-check
compliance-log verify-bundle --tarball ./audit_bundle.tar
```

---

## Product 2 — Proxy-Risk Gateway

```bash
# Shadow (default) — gates only, no upstream call
proxy-risk evaluate \
  --client-id broker-1 \
  --reference-price 10.5 \
  --body '{"symbol":"AAPL","qty":100}' \
  --database ./data/demo_proxy.sqlite

# Live forward — requires PROXY_RISK_UPSTREAM_BASE (+ optional PROXY_RISK_UPSTREAM_TOKEN)
export PROXY_RISK_UPSTREAM_BASE=https://httpbin.org
proxy-risk evaluate --live --client-id broker-1 --method POST --path /post --body '{"ok":true}'

proxy-risk check --database ./data/demo_proxy.sqlite
proxy-risk export --database ./data/demo_proxy.sqlite --repro-check
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
| Proxy-Risk live upstream forward | **Done** — use `--live` + `PROXY_RISK_UPSTREAM_BASE` |
| Health Telemetry (#7) | Do not list |

---

## Related docs

- `docs/INST_PLUS_STRATEGY.md` — portfolio strategy
- `docs/AD_GUARD_INSTITUTIONAL_STACK.md` — enterprise positioning
- `docs/NEW_PRODUCT_INST_PLUS_ROADMAPS.md` — technical roadmaps
