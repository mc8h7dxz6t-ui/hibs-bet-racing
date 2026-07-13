# Institutional++ — Buyer Diligence Scope (11 Platforms)

**Audience:** Technical diligence, procurement, model risk, platform engineering, auditors  
**Scope:** Standalone Inst++ SKUs only — **no Inst++ pricing** in this document  
**Excluded:** ModelGovernor (#8), `inst_spine` (shared library, not a sellable platform), governor consumer apps (sports/trading overlay), and sales bundle labels (`Finance Governor`, `Insurance Governor`, `demo-gold` walkthrough)  
**Date:** July 2026

> **Pack index:** [INST_PLUS_DILIGENCE_PACK.md](INST_PLUS_DILIGENCE_PACK.md)  
> **Per-SKU buyer one-pagers:** `docs/*_BUYER.md`  
> **Per-SKU technical specs:** `docs/*_SALES_TECH_SPEC.md`  
> **Capability compare:** [INST_PLUS_PLATFORM_COMPARE.md](INST_PLUS_PLATFORM_COMPARE.md)

---

## How to read this document

Each platform section includes:

| Block | Content |
|-------|---------|
| **What it does** | One-job statement and buyer pain |
| **Real-world example** | Concrete deployment scenario (not demo fiction) |
| **Tech spec brief** | Ingress, storage, gates, CLI, integrations |
| **Ratings** | Architecture · Code · Execution (1–5) |
| **Market position** | Category, closest comps, capability overlap (no pricing) |

### Rating scale (1–5)

| Score | Architecture | Code | Execution |
|-------|--------------|------|-----------|
| **5** | Clear boundaries, spine-native, documented scale path | Deep tests, rigorous E2E, low coupling | Single-instance VPC complete; CI + demo proven |
| **4** | Solid design; scale items documented as SOW | Good coverage; some integration glue | Prod envelope done; multi-instance needs Redis/Postgres profile |
| **3** | Works; extension points thin | Adequate; buyer-specific adapters needed | Shadow/demo strong; live buyer config is SOW |
| **2** | Conceptual or tightly coupled | Sparse tests or monorepo noise | Proof-of-concept only |
| **1** | Not production-shaped | Unmaintained / unsafe | Not runnable |

**Evidence basis:** 246+ smoke tests, 45 rigorous E2E sections, `verify-bundle` on every SKU, [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md), [INST_PLUS_PRODUCTION_ARCHITECTURE.md](INST_PLUS_PRODUCTION_ARCHITECTURE.md).

---

## Portfolio at a glance

| # | Platform | SKU | Architecture | Code | Execution | Industry gold |
|---|----------|-----|:------------:|:----:|:---------:|:-------------:|
| 1 | Compliance Logger | `compliance-log` | 5 | 4 | 5 | ✅ |
| 2 | Proxy-Risk | `proxy-risk` | 5 | 5 | 5 | ✅ |
| 3 | Alt-Data | `altdata` | 4 | 4 | 4 | ✅ |
| 4 | AI Kit | `ai-kit` | 4 | 4 | 4 | ✅ |
| 5 | Webhook Mesh | `webhook-mesh` | 5 | 5 | 5 | ✅ |
| 6 | Ad Guard | `ad-guard` | 4 | 4 | 5 | ✅ |
| 7 | Health Telemetry | `health-telemetry` | 5 | 5 | 5 | ✅ |
| 9 | Drift Gate | `drift-gate` | 5 | 5 | 5 | ✅ |
| 10 | Webhook Replay | `webhook-replay` | 4 | 4 | 5 | ✅ |
| 11 | Spend Guard | `spend-guard` | 5 | 5 | 5 | ✅ |
| 12 | Agent Ledger | `agent-ledger` | 5 | 4 | 5 | ✅ |

**Shared dependency:** All platforms write to an append-only ledger via `inst_spine` (genesis hash chain, Lamport clocks, F1–F9 institutional check, deterministic `export` + offline `verify-bundle`). The spine is **licensed with each SKU**, not sold separately.

---

## 1 — Compliance Logger

**SKU:** `compliance-log` · **Code:** `src/compliance_log/` (~430 LOC product) · **Serve:** `:8785`

### What it does

Tamper-evident audit trail for **regulated business decisions** — approve, deny, escalate — with snapshot + outcome on a genesis hash chain. Exports a deterministic tarball an auditor verifies **without network access**.

**Buyer pain:** “Prove what the system decided on date X” when CSV exports and dashboard screenshots are not defensible.

### Real-world example

A **payments ops team** logs every automated fraud decision: input snapshot (account age, velocity, rule hits), outcome (`approve` / `deny` / `escalate`), and actor. Monthly, internal audit runs `compliance-log verify-bundle` on the exported tarball in an air-gapped review VM — no callback to vendor SaaS.

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Ingress** | CLI `ingest`, HTTP `POST` on serve, Proof Console guided ingest |
| **Ledger** | `compliance.sqlite` — AppendOnlyLedger + WAL |
| **Gates** | F1–F9 institutional check; F7 coverage on snapshot fields; F9 deterministic export hash |
| **Export** | `export` → tar + SHA256 sidecar + optional HMAC; `verify-bundle` offline |
| **Security** | mTLS ingest (rigorous phase 3); epoch roots in export bundle |
| **Scale** | Single-instance VPC default; optional Postgres profile for multi-tenant ledger |
| **Non-goals** | GRC workflow (ServiceNow), e-discovery UI, SIEM replacement |

```bash
./scripts/demo_compliance_logger.sh
compliance-log verify-bundle --tarball ./data/demo/portfolio/compliance_bundle.tar
```

**Deep spec:** [COMPLIANCE_LOGGER_SALES_TECH_SPEC.md](COMPLIANCE_LOGGER_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 5 | Pure decision-event contract; minimal surface; spine-native |
| **Code** | 4 | Focused package; relies on spine for heavy lifting; serve + CLI tested |
| **Execution** | 5 | Prod ✅ single-instance; Proof Console #1 ingest; rigorous E2E passed |


---

## 2 — Proxy-Risk

**SKU:** `proxy-risk` · **Code:** `src/proxy_risk/` (~900 LOC) · **Serve:** `:8786`

### What it does

Outbound API **firewall** — every request passes circuit → schema → token bucket → idempotency → Z-score drift before shadow or live forward. Every gate outcome is genesis-logged.

**Buyer pain:** Runaway outbound API calls after a bug, fat-finger config, or retry storm — with no audit trail at the proxy layer.

### Real-world example

A **brokerage platform** puts Proxy-Risk in front of their order-routing API. Week one: **shadow mode** — gates run, no upstream calls, ledger proves kill-switch would have fired on the March incident replay. Week four: **live mode** with Redis idempotency across three pods; compliance exports the March dispute bundle offline.

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Hot path** | `ProxyRiskGateway.evaluate` — in-memory gate chain |
| **Modes** | Shadow (no upstream); Live (WAL before upstream; 4xx/5xx → REJECT) |
| **Ledger** | `proxy_risk_ledger.sqlite` |
| **Integrations** | Optional `PROXY_DRIFT_BASELINE` → Drift Gate (#9) on feature vectors |
| **Scale** | `INST_REDIS_URL` for multi-instance token bucket + idempotency (fail-closed) |
| **Latency** | p99 &lt; 10ms shadow (industry gold bench) |
| **Non-goals** | Sub-5ms RTB; inbound webhooks (#5); HashiCorp Vault in P1 |

```bash
./scripts/demo_proxy_risk.sh
proxy-risk evaluate --path /orders --body '{"symbol":"AAPL"}'   # shadow default
```

**Deep spec:** [PROXY_RISK_SALES_TECH_SPEC.md](PROXY_RISK_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 5 | Clear gate chain; shadow→live burn-in; drift integration hook |
| **Code** | 5 | Deepest hot-path SKU; serve + middleware + Redis paths tested |
| **Execution** | 5 | Prod ✅; p99 documented; chaos + industry gold coverage |


---

## 3 — Alt-Data

**SKU:** `altdata` · **Code:** `src/altdata/` (~665 LOC) · **Serve:** `:8787`

### What it does

Alt-data feed poller with **coverage SLA** — 4-rung fetch ladder (primary → mirror → HTML → structural rescue), F7 fail-closed when coverage drops, tamper-evident poll log per cycle.

**Buyer pain:** Silent data gaps when vendor APIs change shape — discovered only after a model trade goes wrong.

### Real-world example

A **quant research desk** polls a commercial alt-data endpoint daily. When the vendor returns empty JSON for two days, Alt-Data raises `CoverageError` and **stops downstream model refresh** instead of training on partial garbage. The poll ledger exports for the model risk committee.

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Ingress** | `poll_once` — stub ctx demo or `--url` live fetch |
| **Ladder** | primary → mirror → HTML scrape → structural rescue (golden path in tests) |
| **Ledger** | `altdata.sqlite` — one genesis entry per poll |
| **Gates** | F7 coverage floor; F9 deterministic export |
| **Buyer SOW** | Live feed URL targets and field schema mapping per buyer |
| **Non-goals** | Full ETL (Fivetran); exchange tick latency |

```bash
./scripts/demo_altdata.sh
altdata poll --feed demo_feed --ctx '{"demo_price":42.5,"demo_seats":180}'
```

**Deep spec:** [ALTDATA_SALES_TECH_SPEC.md](ALTDATA_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 4 | Solid ladder + coverage gate; buyer feed registry is integration SOW |
| **Code** | 4 | Structural golden tests; production feed adapters vary by buyer |
| **Execution** | 4 | Prod ✅ for envelope; live URL feeds need buyer-specific config |


---

## 4 — AI Kit

**SKU:** `ai-kit` · **Code:** `src/ai_kit/` (~610 LOC) · **CLI only** (no HTTP serve)

### What it does

Production **agent guardrails** — rate limits, Lamport checkpoints for crash-safe resume, structured output validation, tamper-evident trace ledger. Buyer supplies `step_fn` (LLM or rules).

**Buyer pain:** Agent workers crash mid-run, blow rate limits, or produce unvalidated JSON — with no exportable trace for compliance.

### Real-world example

A **platform team** runs a 12-step document-extraction agent. AI Kit checkpoints after each step; on worker restart, resume from last Lamport checkpoint. Monthly, risk exports the trace bundle and verifies offline — “show me every tool invocation in Q2.”

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Runtime** | `AgentLoop.run_steps` with `step_fn` injection |
| **Ledger** | `ai_kit_trace.sqlite` |
| **Capabilities** | Token bucket rates; `validate_with_retry`; checkpoint resume |
| **Gates** | F1–F9 on trace ledger |
| **Non-goals** | Hosted LLM; vector DB; LangGraph UI |

```bash
./scripts/demo_ai_kit.sh
ai-kit run --steps 3 --trace-db ./trace.sqlite
```

**Deep spec:** [AI_KIT_SALES_TECH_SPEC.md](AI_KIT_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 4 | Clean step_fn contract; not a full agent framework |
| **Code** | 4 | CLI + LLM optional path tested; hardest standalone GTM sell |
| **Execution** | 4 | Prod ✅ envelope; buyer wires step_fn into their runtime |


---

## 5 — Webhook Mesh

**SKU:** `webhook-mesh` · **Code:** `src/webhook_mesh/` (~1,320 LOC) · **Serve:** `:8787`

### What it does

Inbound webhook **idempotency mesh** — HMAC verify → Redis SETNX idempotency → WAL fsync → HTTP 200 → async Redis Stream forward. Never double-process a billing event.

**Buyer pain:** Stripe/Shopify sends duplicate webhooks; in-memory dedupe fails across pods; finance finds double charges days later.

### Real-world example

A **B2B SaaS billing team** terminates Stripe webhooks at Webhook Mesh. Three Kubernetes replicas share Redis idempotency. On duplicate `invoice.paid`, second delivery gets 200 with `idempotent: true` but **no second side effect**. Capture dir feeds Webhook Replay (#10) for dispute forensics.

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Ingress path** | HMAC → idempotency CAS → WAL fsync → 200 → stream forward |
| **Routes** | Stripe, Shopify header mapping; generic HMAC |
| **Ledger** | `webhook_mesh.sqlite` — cold-path genesis append |
| **Scale** | `INST_REDIS_URL` required for multi-instance; XAUTOCLAIM reclaim (phase 3) |
| **Capture** | `WEBHOOK_REPLAY_CAPTURE_DIR` → `.wrcap` for #10 |
| **Non-goals** | Full event bus (Kafka); Stripe Connect dashboard |

```bash
export WEBHOOK_PROVIDER_SECRET=demo-secret
./scripts/demo_webhook_mesh.sh
```

**Deep spec:** [WEBHOOK_MESH_SALES_TECH_SPEC.md](WEBHOOK_MESH_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 5 | WAL-before-ack is the right invariant; stream + capture integration |
| **Code** | 5 | Largest ingress SKU; chaos tests; Redis soak in CI |
| **Execution** | 5 | Prod ✅; docker-extended zero-skip; pairs with #10 |


---

## 6 — Ad Guard

**SKU:** `ad-guard` · **Code:** `src/ad_guard/` (~790 LOC) · **Serve:** `:8788`

### What it does

Marketing API **spend kill** at the boundary — Google/Meta spend parsers, per-campaign token bucket, Z-score velocity kill, genesis audit before dollars leave the account.

**Buyer pain:** Misconfigured campaign API calls burn budget overnight; finance only learns from post-hoc alerts.

### Real-world example

A **growth agency** proxies Google Ads API bid updates through Ad Guard. A script bug sends 10× normal bid velocity; Z-score kill fires, request rejected, kill event on genesis chain. Finance verifies the kill bundle without accessing the ad platform.

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Hot path** | Same shadow/live pattern as Proxy-Risk |
| **Parsers** | Google `bidMicros`, Meta `daily_budget` built-in |
| **Ledger** | `ad_guard.sqlite` |
| **Stack position** | NeMo/Bedrock (safety) → **Ad Guard** (spend) → DSP + DV/IAS (placement) |
| **Non-goals** | RTB sub-5ms; DoubleVerify pre-bid; DSP UI |

```bash
./scripts/demo_ad_guard.sh
ad-guard evaluate --provider google --body '{"campaignId":"12345","bidMicros":2500000}'
```

**Deep spec:** [AD_GUARD_SALES_TECH_SPEC.md](AD_GUARD_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 4 | Reuses proxy patterns well; parser surface is finite |
| **Code** | 4 | Creative header fuzz (phase 3); Google/Meta paths tested |
| **Execution** | 5 | Prod ✅; shadow burn-in default |


---

## 7 — Health Telemetry

**SKU:** `health-telemetry` · **Code:** `src/health_telemetry/` (~890 LOC) · **Serve:** `:8793`

### What it does

Device batch **tamper evidence** — schema + per-device sequence gate, optional WAL-before-ack HTTP ingress, PHI-safe observation-lane export. **Audit spine, not FDA certification.**

**Buyer pain:** Remote patient monitoring vendor must prove telemetry batches were not altered or replayed — without buying an EMR.

### Real-world example

An **RPM vendor** ingests ward-scale pulse-ox batches via `POST /v1/telemetry/batch`. Each `device_id` has monotonic `seq`; gap or backward seq → reject. Compliance exports `--observation-lane` bundle (summaries only) for NHS-adjacent diligence review.

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Ingress** | CLI `ingest_batch`; HTTP serve with WAL fsync |
| **Sequence gate** | Per-device `seq` fail-closed (replay/gap attack resistant) |
| **Ledger** | `health.sqlite` |
| **PHI** | `--observation-lane` redacted export |
| **Diligence pack** | [HEALTH_TELEMETRY_HIPAA_PACK.md](HEALTH_TELEMETRY_HIPAA_PACK.md) template |
| **Non-goals** | FDA/UKCA cert; EMR/FHIR P1; clinical alerting UI |

```bash
./scripts/demo_health_telemetry.sh
health-telemetry export --observation-lane --tarball ./health_obs.tar
```

**Deep spec:** [HEALTH_TELEMETRY_SALES_TECH_SPEC.md](HEALTH_TELEMETRY_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 5 | Sequence gate + observation lane = right health posture |
| **Code** | 5 | Ingest, serve, export paths well tested |
| **Execution** | 5 | Prod ✅; HIPAA template for buyer questionnaires |


---

## 9 — Drift Gate

**SKU:** `drift-gate` · **Code:** `src/drift_gate/` (~825 LOC) · **CLI / integrate hook**

### What it does

PSI/KS **statistical drift interceptor** on live feature vectors — shadow burn-in, then inline enforce (reject/kill) with genesis audit per evaluation.

**Buyer pain:** Model observability emails arrive Monday; the bad model served all weekend.

### Real-world example

A **regulated lender** attaches Drift Gate to the credit-scoring API via Proxy-Risk (`PROXY_DRIFT_BASELINE`). Two weeks shadow: drift logged, traffic passes. Enforce mode: PSI breach on `income_band` blocks inference and logs `drift_gate_evaluation` for MRM.

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Metrics** | PSI + KS per feature vs stored baseline |
| **Modes** | Shadow (log only); Enforce (block) |
| **State** | File or Redis rolling windows (`INST_REDIS_URL`) |
| **Integration** | `PROXY_DRIFT_BASELINE` on Proxy-Risk hot path |
| **Ledger** | `drift_gate.sqlite` |
| **Non-goals** | Full MRM platform (Fiddler); fairness certification |

```bash
./scripts/demo_drift_gate.sh
drift-gate evaluate --baseline ./baseline.json --features '{"f1":0.2,"f2":0.8}'
```

**Deep spec:** [DRIFT_GATE_SALES_TECH_SPEC.md](DRIFT_GATE_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 5 | Inline enforce + proxy hook = production-shaped |
| **Code** | 5 | Golden matrices; Redis rolling windows tested |
| **Execution** | 5 | Prod ✅; shadow→enforce documented |


---

## 10 — Webhook Replay

**SKU:** `webhook-replay` · **Code:** `src/webhook_replay/` (~535 LOC) · **CLI / capture hook**

### What it does

Capture **raw webhook ingress bytes** (`.wrcap`), replay offline without network, prove idempotent outcomes and tamper detection via genesis audit.

**Buyer pain:** “What exact bytes caused the duplicate charge?” — SaaS replay needs network; scripts are not evidence.

### Real-world example

After a **billing dispute**, ops pulls `.wrcap` files from Webhook Mesh capture dir. Legal runs `webhook-replay replay` air-gapped; second replay proves idempotent handling; bundle exports for counsel.

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Format** | `.wrcap` — mmap-readable, `payload_sha256` manifest |
| **Replay** | Air-gapped — no network in replay mode |
| **Integration** | `WEBHOOK_REPLAY_CAPTURE_DIR` on Mesh (#5) |
| **Ledger** | `webhook_replay.sqlite` |
| **Non-goals** | Hookdeck/Svix delivery platform; Kafka scale |

```bash
./scripts/demo_webhook_replay.sh
webhook-replay replay --capture ./captures/event.wrcap
```

**Deep spec:** [WEBHOOK_REPLAY_SALES_TECH_SPEC.md](WEBHOOK_REPLAY_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 4 | Focused forensic tool; depends on #5 for capture |
| **Code** | 4 | Byte-identical replay proven; smaller surface |
| **Execution** | 5 | Prod ✅; pairs cleanly with Mesh |


---

## 11 — Spend Guard

**SKU:** `spend-guard` · **Code:** `src/spend_guard/` (~1,390 LOC) · **Serve:** `:8789`

### What it does

**Reserve-before-dispatch** API spend wallet — hold estimated cost before upstream clears, settle on actual cost, freeze wallet on spend drift. OpenAI-compat gateway optional.

**Buyer pain:** LLM/API spend runaway over a weekend; budgets track spend but do not **block** dispatch.

### Real-world example

An **AI platform team** puts Spend Guard in front of OpenAI-compatible inference. Each chat completion: `reserve(estimate)` → upstream call → `settle(actual)`. Retry storm hits same `request_id` — idempotent hold. Drift lockout freezes wallet when settle pattern exceeds threshold.

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Wallet** | SQLite IMMEDIATE transactions default; Postgres profile optional |
| **Semantics** | Reserve → settle → drift lockout (`DRIFT_THRESHOLD_EXCEEDED`) |
| **Gateway** | `SpendGuardGateway` — `/v1/chat/completions` OpenAI-compat |
| **Ledger** | `spend_guard.sqlite` — genesis spend events |
| **Idempotency** | `request_id` hold dedupe |
| **Non-goals** | LiteLLM routing catalog; multi-currency treasury |

```bash
./scripts/demo_spend_guard.sh
spend-guard verify-bundle --tarball ./data/demo/spend_guard_bundle.tar
```

**Deep spec:** [SPEND_GUARD_SALES_TECH_SPEC.md](SPEND_GUARD_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 5 | Reserve/settle/lockout is the right money semantics |
| **Code** | 5 | Largest wallet surface; Postgres profile; gateway tested |
| **Execution** | 5 | Prod ✅; rigorous idempotency + drift lock proven |


---

## 12 — Agent Ledger

**SKU:** `agent-ledger` · **Code:** `src/agent_ledger/` (~1,010 LOC) · **Serve:** `:8792`

### What it does

Fail-closed **runtime governance for agent tool calls** — authorize before invoke, deny/escalate with argument guards, human attestation on critical tools, genesis audit chain.

**Buyer pain:** “What did the agent actually do?” — trace logs are editable; no proof of pre-execution authorization.

### Real-world example

A **fintech ops agent** proposes `transfer_funds(amount, account)`. Agent Ledger checks risk tier + argument guards (SQL/path traversal fail-closed). Critical tier → escalation lane until `human_approved`. Auditor verifies authorize→complete chain offline.

### Tech spec brief

| Layer | Detail |
|-------|--------|
| **Flow** | `authorize_tool_call` → execute (buyer runtime) → `complete_tool_call` |
| **Policy** | Risk tiers low → critical; agent ceiling; argument guards |
| **Shadow** | Log-without-block burn-in (Proxy-Risk pattern) |
| **Ledger** | `agent_ledger.sqlite` |
| **Integrate** | LangChain hook documented |
| **Non-goals** | Full agent framework; LLM spend (#11); content moderation |

```bash
./scripts/demo_agent_ledger.sh
agent-ledger verify-bundle --tarball ./data/demo/agent_ledger_bundle.tar
```

**Deep spec:** [AGENT_LEDGER_SALES_TECH_SPEC.md](AGENT_LEDGER_SALES_TECH_SPEC.md)

### Ratings

| Dimension | Score | Rationale |
|-----------|:-----:|-----------|
| **Architecture** | 5 | Authorize-before-invoke is the right security invariant |
| **Code** | 4 | Solid core; buyer agent runtime wiring is integration |
| **Execution** | 5 | Prod ✅; deny/escalate rigorous pass |


---

## Composite diligence summary

### What you are buying (11 platforms, no governor SKU)

| Asset class | Description |
|-------------|-------------|
| **Product code** | 11 deployable SKUs (~8,400 LOC product + ~3,700 LOC shared spine) |
| **Proof package** | 246+ smoke tests, 45 rigorous E2E sections, `PORTFOLIO_MANIFEST.json`, buyer + sales specs |
| **Deployment model** | Air-gap VPC, SQLite default, optional Redis/Postgres scale profiles |
| **Honest limits** | Pre-revenue; no SOC2 Type II attestation; Python hot path; monorepo sports adjacency |

### Diligence tier (qualitative)

| Tier | Platforms | Rationale |
|------|-----------|-----------|
| **Tier A — strongest diligence wedge** | #1, #2, #5, #7, #9, #11, #12 | Clear buyer pain, offline proof, rigorous E2E |
| **Tier B — solid, often bundled** | #6, #10 | Strong as attach; narrower standalone GTM |
| **Tier C — integration SOW** | #3, #4 | Real product; buyer feed / agent runtime wiring required |

### When Inst++ wins vs market

| Buyer priority | Market stack wins | Inst++ (11 SKUs) wins |
|----------------|-------------------|------------------------|
| Fastest time-to-dashboard | Langfuse, Hookdeck, Fiddler SaaS | — |
| Auditor offline proof | Weak across SaaS | **verify-bundle 11/11** |
| Webhook never-double-charge proof | Partial | **#5 + #10 chain** |
| Outbound API kill + audit | Access logs only | **#2 + #9** |
| LLM spend block before inference | Budget alerts | **#11 reserve/settle/lock** |
| Agent tool authorization proof | Post-hoc traces | **#12 pre-exec chain** |
| High-volume metered SaaS | Per-message / per-trace billing | **Flat VPC** deploy model |

### Diligence draggers (honest)

| Drag | Effect |
|------|--------|
| No revenue / no LOI | Buyer must evaluate on proof package |
| Shared monorepo with sports stack | Buyer must scope SKU extract |
| No SOC2 Type II | Enterprise security questionnaire friction |
| Python hot path | Quant/latency buyers may discount |
| GitHub Actions billing blocked | CI green requires account fix — code tested locally |


## 15-minute diligence run

```bash
pip install -e ".[dev,instpp]"
make plug                                    # demo-all 11 (+ MG if full portfolio) + verify
./scripts/instpp_smoke_test.sh               # 246+ tests
./scripts/instpp_rigorous_test.sh            # per-SKU E2E → docs/test_logs/
cat docs/test_logs/instpp_rigorous_latest_summary.json
```

Per platform:

```bash
./scripts/demo_<sku>.sh
<sku-cli> verify-bundle --tarball ./data/demo/portfolio/<sku>_bundle.tar
```

Proof Console (guided ingest all SKUs): `make workflow-serve` → `:8790`

---

## Related documents

| Document | Purpose |
|----------|---------|
| [PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md](PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md) | Sales positioning per SKU |
| [INST_PLUS_PLATFORM_COMPARE.md](INST_PLUS_PLATFORM_COMPARE.md) | Capability matrix vs adjacent platforms |
| [PORTFOLIO_EVIDENCE_SHEET.md](PORTFOLIO_EVIDENCE_SHEET.md) | CI artifacts and test file index |
| [FORENSIC_ARCHITECTURE_TRUTH.md](FORENSIC_ARCHITECTURE_TRUTH.md) | Honest scope vs external rebrands |
| [SOC2_VPC_DILIGENCE_PACK.md](SOC2_VPC_DILIGENCE_PACK.md) | VPC evidence template (not attestation) |
