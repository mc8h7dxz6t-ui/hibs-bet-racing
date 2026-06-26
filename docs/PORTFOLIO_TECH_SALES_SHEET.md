# Portfolio — Full Tech & Sales Sheet

**Audience:** Procurement, platform engineering, CFO sponsors, technical evaluators  
**Posture:** Air-gap VPC audit infrastructure — prove with math, not slides  
**Proof:** 91 automated tests · rigorous E2E 8/8 · offline `verify-bundle` on every SKU  
**Date:** June 2026

> **Valuation / exit framing is at the bottom** — [Value today](#value-today). Everything above is license economics, competitive positioning, and technical proof only.

---

## Portfolio pitch

*Eight deployable products, one cryptographic audit spine — every gate decision exportable and verifiable without calling the vendor.*

| # | Product | SKU | Demo |
|---|---------|-----|------|
| 1 | Compliance Logger | `compliance-log` | `./scripts/demo_compliance_logger.sh` |
| 2 | Proxy-Risk | `proxy-risk` | `./scripts/demo_proxy_risk.sh` |
| 3 | Alt-Data | `altdata` | `./scripts/demo_altdata.sh` |
| 4 | AI Kit | `ai-kit` | `./scripts/demo_ai_kit.sh` |
| 5 | Webhook Mesh | `webhook-mesh` | `./scripts/demo_webhook_mesh.sh` |
| 6 | Ad Guard | `ad-guard` | `./scripts/demo_ad_guard.sh` |
| 7 | Health Telemetry | `health-telemetry` | `./scripts/demo_health_telemetry.sh` |
| 8 | ModelGovernor | `model-governor` | `./scripts/demo_model_governor.sh` · `make demo-gold` (LLM spend plane) |

**Deep specs:** `docs/*_SALES_TECH_SPEC.md` · **Buyer one-pagers:** `docs/*_BUYER.md`

---

## Shared spine — why every SKU is credible

| Pain | Industry default | Portfolio answer |
|------|------------------|------------------|
| “Prove what happened on date X” | Editable CSV / dashboard trust | Genesis hash chain + deterministic export |
| Auditor needs offline replay | Vendor callback / live DB | `verify-bundle` on tarball only |
| Clock spoofing / device drift | Wall-clock timestamps | Lamport logical clocks (F4) |
| Silent data gaps | Alert after the fact | Fail-closed gates (F7 coverage, rate limits) |
| Vendor lock-in | SaaS-only | Air-gap VPC — buyer holds ledger |
| Multi-instance dedupe | In-memory only | Redis fail-closed CAS |

**Commercial packaging**

| Package | Contents |
|---------|----------|
| Single SKU license | CLI + spine + export + verify-bundle + demo script |
| Spine bundle (2+ SKUs) | Shared `inst_spine`, unified export — **15% discount** on 2nd+ SKU |
| Design partner SOW | Live URL / schema mapping | £2k–£8k one-time |
| Maintenance | Security patches, spine upgrades | 15–20% ARR |

---

## Revenue summary (realistic license / mo)

Assumptions for all products below:

- **VPC / on-prem license** — not multi-tenant SaaS list price
- **Y1 conservative** = 3–5 paying tenants, mostly mid-band ACV, long sales cycles
- **Y1 stretch** = 8–12 tenants or one anchor deal pulling average up
- **Y2** = 15–25 tenants across a SKU **if** one design partner converts and word-of-mouth in a vertical
- **Pre-revenue today** — these are *capable* bands, not booked ARR

| # | Product | License / mo | Y1 conservative ARR | Y1 stretch ARR | Y2 capable ARR |
|---|---------|--------------|----------------------|----------------|----------------|
| 1 | Compliance Logger | £300–£800 | £11k–£48k | £29k–£96k | £54k–£240k |
| 2 | Proxy-Risk | £400–£1,200 | £14k–£72k | £38k–£144k | £72k–£360k |
| 3 | Alt-Data | £500–£2,000 / feed | £18k–£120k | £48k–£240k | £90k–£600k |
| 4 | AI Kit | £50–£249 / seat | £3k–£15k | £8k–£36k | £15k–£90k |
| 5 | Webhook Mesh | £199–£599 | £7k–£36k | £19k–£72k | £36k–£180k |
| 6 | Ad Guard | £300–£800 | £11k–£48k | £29k–£96k | £54k–£240k |
| 7 | Health Telemetry | £5k–£15k + £500/mo | £17k–£84k | £44k–£168k | £83k–£390k |
| 8a | ModelGovernor (lifecycle CLI) | £400–£1,000 | £14k–£60k | £38k–£120k | £72k–£300k |
| 8b | ModelGovernor (LLM spend plane) | £1,500–£5,000 | £18k–£120k | £54k–£300k | £108k–£600k |
| **Portfolio (all SKUs, no double-count)** | Bundle discount | — | **£120k–£350k** | **£280k–£700k** | **£500k–£1.5M** |

*Portfolio totals assume a holding co or integrator buys 3–5 SKUs, not eight independent GTM motions at once.*

### Completion legend

| Symbol | Meaning |
|--------|---------|
| ✅ | **Complete** — shipped, tested, documented |
| 🟡 | **Partial** — works with documented caveats or design-partner SOW |
| 🔲 | **Not started** — roadmap, explicit non-goal, or out of SKU scope |

**Layers:** **Inst** = institutional gold (CLI, F1–F9, verify-bundle, unit + rigorous E2E) · **Prod** = production VPC deploy · **Comm** = buyer doc + sales spec + demo · **GTM** = paying tenants / LOI

### Completion at a glance

| # | Product | Grade | Inst | Prod | Comm | GTM | Headline gap |
|---|---------|-------|------|------|------|-----|--------------|
| 1 | Compliance Logger | **Gold** | ✅ | ✅ | ✅ | 🔲 | No GRC workflow / SOC 2 SaaS |
| 2 | Proxy-Risk | **Gold** | ✅ | 🟡 | ✅ | 🔲 | Redis required for multi-instance live |
| 3 | Alt-Data | **Gold** | ✅ | 🟡 | ✅ | 🔲 | Buyer feeds need design-partner SOW |
| 4 | AI Kit | **Gold** | ✅ | 🟡 | ✅ | 🔲 | Hardest standalone sell; no workflow UI |
| 5 | Webhook Mesh | **Gold** | ✅ | 🟡 | ✅ | 🔲 | Queue durability → Redis Stream in prod |
| 6 | Ad Guard | **Gold** | ✅ | 🟡 | ✅ | 🔲 | Not RTB / DSP UI |
| 7 | Health Telemetry | **Gold** | ✅ | 🟡 | ✅ | 🔲 | No FDA / EMR / clinical UI |
| 8a | ModelGovernor lifecycle | **Gold** | ✅ | ✅ | ✅ | 🔲 | Not full MLOps platform |
| 8b | ModelGovernor spend plane | **Demo gold** | 🟡 | 🟡 | ✅ | 🔲 | Not in `instpp_rigorous` CI; no managed SaaS |
| — | **Shared `inst_spine`** | **Gold** | ✅ | ✅ | ✅ | — | 91 tests · 8/8 rigorous E2E (June 2026) |

**Portfolio GTM (all SKUs):** 🔲 pre-revenue · 🔲 no signed LOI · 🔲 no SOC 2 Type II certified SaaS (VPC pack only)

---

# Per platform

---

## 1 — Compliance Logger

**One job:** Tamper-proof regulated **business decision** audit — snapshot + outcome + hash chain, offline `verify-bundle`.

**Pitch:** *Prove the approval on date X — with math, not a spreadsheet.*

### License economics

| Band | £/mo | Typical buyer |
|------|------|---------------|
| Standard | £300–£500 | Single business unit, one decision type |
| Regulated | £500–£800 | Fintech / lending with auditor dry-run requirement |

| Scenario | Tenants | Avg £/mo | ARR | Why it's realistic |
|----------|---------|----------|-----|-------------------|
| Y1 conservative | 3–5 | £400 | **£14k–£24k** | One fintech pilot + 2 NGB/adjacent — compliance infra is slow but sticky |
| Y1 stretch | 8–10 | £550 | **£53k–£66k** | Anchor fintech (£800) + 7 mid-market |
| Y2 capable | 15–20 | £600 | **£108k–£144k** | Repeatable VPC deploy; auditor letter unlocks second vertical |

**Why this price vs market:** GRC SaaS (Archer, ServiceNow) is £50k–£200k+/yr but includes workflow UI you don't need. immudb/QLDB-class immutability is BYO-everything. You sit at **10–20% of GRC ACV** for the audit spine only — easy CFO line item if legal already asked for tamper evidence.

### Problem → solution

| Buyer pain | Industry default | Compliance Logger |
|------------|------------------|-------------------|
| “Prove decision on date X” | CSV/PDF (editable) | Snapshot + outcome + hash chain |
| Auditor distrust | “Trust our dashboard” | Offline `verify-bundle` |
| Clock spoofing | Wall-clock timestamps | Lamport clocks (F4) |
| Reproducibility disputes | Non-deterministic exports | F9 — identical ledger → identical SHA256 |

### Competitive comparison

| Capability | GRC SaaS | immudb / QLDB | **Compliance Logger** |
|------------|----------|---------------|----------------------|
| Decision snapshot contract | Custom fields | BYO schema | **First-class ingest** |
| Offline auditor replay | No | Partial (needs DB) | **Tarball only** |
| Deterministic export hash | No | No | **F9 gate** |
| Workflow UI | Strong | None | **5-step proof console** |
| Air-gap default | Rare | Yes | **Yes** |

**Win when:** buyer needs **proof**, not case management.  
**Lose when:** buyer needs ServiceNow workflow or certified multi-tenant SaaS day one.

**Demo:** `./scripts/demo_compliance_logger.sh` · **Spec:** [COMPLIANCE_LOGGER_SALES_TECH_SPEC.md](COMPLIANCE_LOGGER_SALES_TECH_SPEC.md)

### Completion status

| Layer | Status | Detail |
|-------|--------|--------|
| **Institutional gold** | ✅ | `record` / `check` / `export` / `verify-bundle`; F1–F9; in rigorous E2E |
| **Production deploy** | ✅ | Air-gap SQLite + WAL; export aborts on gate failure |
| **Workflow UI** | ✅ | `inst-workflow serve --product compliance` (5-step proof console) |
| **Commercial pack** | ✅ | Buyer sheet, sales spec, `demo_compliance_logger.sh` |
| **GTM** | 🔲 | No paying tenants; no tier-1 LOI |
| **Explicit non-goals** | — | ServiceNow/Archer GRC · SIEM · e-discovery · multi-tenant SOC 2 SaaS |

**CI proof:** `compliance_logger` in `instpp_rigorous_latest_summary.json` — **PASSED**

---

## 2 — Proxy-Risk

**One job:** Outbound API **firewall** — rate limit, Z-score kill, idempotency, shadow → live, every gate on chain.

**Pitch:** *Stop runaway outbound API spend and prove every approve/reject/kill.*

### License economics

| Band | £/mo | Typical buyer |
|------|------|---------------|
| Shadow | £400–£700 | Burn-in, no capital at risk |
| Live + Redis | £700–£1,200 | Multi-instance production forward |

| Scenario | Tenants | Avg £/mo | ARR | Why it's realistic |
|----------|---------|----------|-----|-------------------|
| Y1 conservative | 3–4 | £550 | **£20k–£26k** | Broker ops + one payments team — shadow default de-risks sale |
| Y1 stretch | 8–10 | £800 | **£77k–£96k** | One quant shop at £1,200 + mid-market cluster |
| Y2 capable | 12–18 | £900 | **£130k–£194k** | Proxy-Risk is closest to **revenue-ready** — clear ROI when one fat-finger is prevented |

**Why this price vs market:** Kong/Apigee enterprise is £25k–£100k+/yr for routing, not decision audit. WAF SaaS charges per request without genesis proof. **£5k–£15k ACV** is below “procurement committee” threshold at many fintechs but above script-kiddie tooling.

### Problem → solution

| Buyer pain | Industry default | Proxy-Risk |
|------------|------------------|------------|
| Runaway API after bug | Rate limit only | Bucket + Z-score + circuit kill |
| Double-submit billing | Best-effort dedupe | Idempotency CAS (Redis) |
| No proxy audit trail | Access logs (mutable) | Genesis ledger per outcome |
| Fear of going live | All-or-nothing | **Shadow default** |

### Competitive comparison

| Capability | API gateway (Kong) | WAF / rate SaaS | **Proxy-Risk** |
|------------|-------------------|-----------------|----------------|
| Shadow burn-in | No | No | **Default** |
| Kill switch + Z-score | Rare | Sometimes | **Yes** |
| Audit per gate outcome | Access log | Metrics | **Genesis chain** |
| Offline verify | No | No | **verify-bundle** |

**Win when:** fail-closed outbound control + proof.  
**Lose when:** sub-5ms RTB or full API lifecycle platform.

**Demo:** `./scripts/demo_proxy_risk.sh` · **Spec:** [PROXY_RISK_SALES_TECH_SPEC.md](PROXY_RISK_SALES_TECH_SPEC.md)

### Completion status

| Layer | Status | Detail |
|-------|--------|--------|
| **Institutional gold** | ✅ | Full gate chain; shadow + live httpx; every APPROVE/REJECT/KILL on chain |
| **Production deploy** | 🟡 | Shadow default ✅; live needs Redis for token bucket + idempotency; WAL before upstream |
| **Workflow UI** | ✅ | `inst-workflow serve --product proxy` |
| **Commercial pack** | ✅ | Buyer sheet, sales spec, rigorous bench (p99 shadow overhead in tests) |
| **GTM** | 🔲 | **Closest to revenue-ready** — clear ROI story; still no signed tenants |
| **Explicit non-goals** | — | Sub-5ms RTB · Kong/Apigee lifecycle · DV/IAS pre-bid |

**CI proof:** `proxy_risk` in rigorous E2E — **PASSED**

---

## 3 — Alt-Data

**One job:** Clean alt-data feed with **coverage SLA** — 4-rung fetch ladder, F7 fail-closed, tamper-evident poll log.

**Pitch:** *Prove the feed wasn't silently empty on date X.*

### License economics

| Band | £/mo | Typical buyer |
|------|------|---------------|
| Single feed | £500–£1,000 | One symbol class / geography |
| Multi-feed / SLA | £1,000–£2,000 | Quant desk with compliance adjacency |

| Scenario | Feeds | Avg £/mo | ARR | Why it's realistic |
|----------|-------|----------|-----|-------------------|
| Y1 conservative | 3–4 feeds | £700 | **£25k–£34k** | Design-partner pricing on live URL wiring |
| Y1 stretch | 8–10 feeds | £1,000 | **£96k–£120k** | One quant shop standardises on your poll proof |
| Y2 capable | 15–25 feeds | £1,200 | **£216k–£360k** | Per-feed expansion is natural land-and-expand |

**Why this price vs market:** Bloomberg/Refinitiv is £20k+/seat/yr — different buyer. Scraper farms are £0 but no audit. **£6k–£24k/yr per feed** is credible for a desk that already pays for data engineering time to babysit scrapers.

### Problem → solution

| Buyer pain | Industry default | Alt-Data |
|------------|------------------|----------|
| Silent API gaps | Dashboard alert next day | F7 coverage fail-closed |
| ETL logs ≠ audit | Airflow logs | Genesis ledger per poll |
| Primary fetcher down | Manual failover | 4-rung ladder |

### Competitive comparison

| Capability | Generic scrapers | ETL SaaS (Fivetran) | **Alt-Data** |
|------------|------------------|---------------------|--------------|
| Coverage as gate | Ad-hoc | Dashboard | **F7 institutional** |
| Structural rescue | Rare | Manual | **Rung-4 HTML** |
| Tamper-evident poll log | No | No | **Genesis per poll** |
| Offline verify | No | No | **verify-bundle** |

**Win when:** coverage SLA + poll proof.  
**Lose when:** full ETL catalog or exchange tick latency.

**Demo:** `./scripts/demo_altdata.sh` · **Spec:** [ALTDATA_SALES_TECH_SPEC.md](ALTDATA_SALES_TECH_SPEC.md)

### Completion status

| Layer | Status | Detail |
|-------|--------|--------|
| **Institutional gold** | ✅ | F7 coverage gate; 4-rung ladder; `CoverageError` fail-closed; export + verify-bundle |
| **Production deploy** | 🟡 | Built-in `fx_gbp_cross` production feed (Frankfurter HTTP); **buyer-specific feeds** → design-partner SOW (£2k–£8k) |
| **Workflow UI** | 🔲 | CLI only — no browser console |
| **Commercial pack** | ✅ | Buyer sheet, sales spec, `altdata list-feeds` registry |
| **GTM** | 🔲 | No paying feed contracts |
| **Explicit non-goals** | — | Full ETL (Airflow/Fivetran) · exchange tick latency · data catalog UI |

**CI proof:** `altdata` in rigorous E2E — **PASSED**

---

## 4 — AI Kit

**One job:** Production **agent guardrails** — rate limits, Lamport checkpoints, trace ledger, optional live LLM.

**Pitch:** *Run agents in production with checkpoints and an audit trail auditors can verify offline.*

### License economics

| Band | £/mo | Typical buyer |
|------|------|---------------|
| Team (5–10 seats) | £250–£750 | £50–£75/seat effective |
| Platform (25+ seats) | £1,250–£6,225 | £50–£249/seat list |

| Scenario | Seats | Effective £/mo | ARR | Why it's realistic |
|----------|-------|----------------|-----|-------------------|
| Y1 conservative | 50–100 | £400 avg | **£5k–£10k** | Hardest SKU to sell standalone — often bundled with #8 or services |
| Y1 stretch | 200–400 | £75/seat | **£18k–£36k** | Platform team standardises trace export for compliance review |
| Y2 capable | 500–1,000 | £60/seat | **£36k–£72k** | Seat expansion once one agent workflow is production |

**Why this price vs market:** LangSmith / Helicone observability is usage-priced and SaaS-hosted. You are **not** competing on trace UI — you compete on **air-gap trace + verify-bundle** at **seat economics below Copilot add-ons**.

### Problem → solution

| Buyer pain | Industry default | AI Kit |
|------------|------------------|--------|
| Rate limits crash prod | Raw exceptions | Typed `RateLimitError` |
| Lost state on crash | Restart from scratch | Lamport checkpoints |
| Agent audit | Unstructured logs | Trace ledger + export |

### Competitive comparison

| Capability | LangChain defaults | LangSmith / Helicone | **AI Kit** |
|------------|-------------------|----------------------|------------|
| Crash-safe resume | Varies | N/A | **Lamport checkpoints** |
| Agent trace audit | Logs | SaaS dashboard | **Ledger + verify-bundle** |
| Air-gap deploy | Rare | No | **Yes** |
| Structured output retry | Library-specific | N/A | **CLI wired** |

**Win when:** production guardrails + offline trace audit.  
**Lose when:** LangGraph ecosystem, vector DB, hosted observability.

**Demo:** `./scripts/demo_ai_kit.sh` · **Spec:** [AI_KIT_SALES_TECH_SPEC.md](AI_KIT_SALES_TECH_SPEC.md)

### Completion status

| Layer | Status | Detail |
|-------|--------|--------|
| **Institutional gold** | ✅ | Lamport checkpoints; trace ledger; `RateLimitError` typed; `validate_with_retry` in run path |
| **Production deploy** | 🟡 | Stub mode default; `--live-llm` optional (OpenAI-compat); buyer supplies `step_fn` for real agents |
| **Workflow UI** | 🔲 | CLI only |
| **Commercial pack** | ✅ | Buyer sheet, sales spec |
| **GTM** | 🔲 | Weakest standalone SKU — usually bundled with #8 or services |
| **Explicit non-goals** | — | Hosted LLM · LangGraph · vector DB / RAG · NeMo safety inference · multi-agent UI |

**CI proof:** `ai_kit` in rigorous E2E — **PASSED**

---

## 5 — Webhook Mesh

**One job:** **Never double-process** a billing webhook — HMAC verify, Redis idempotency, WAL before 200, genesis ingress ledger.

**Pitch:** *Idempotent Stripe/Shopify ingress with cryptographic proof.*

### License economics

| Band | £/mo | Typical buyer |
|------|------|---------------|
| Single tenant | £199–£399 | Early-stage SaaS |
| Multi-tenant + Redis | £399–£599 | Fintech / billing platform |

| Scenario | Tenants | Avg £/mo | ARR | Why it's realistic |
|----------|---------|----------|-----|-------------------|
| Y1 conservative | 4–6 | £350 | **£17k–£25k** | One double-charge incident pays for 5 years of license |
| Y1 stretch | 10–12 | £450 | **£54k–£65k** | Billing infra teams feel pain acutely |
| Y2 capable | 20–30 | £500 | **£120k–£180k** | Stripe-native routes reduce integration friction |

**Why this price vs market:** Stripe idempotency keys are free but not auditable or multi-provider. Custom middleware is eng time. **£2.4k–£7.2k ACV** is a rounding error vs one billing dispute or duplicate payout.

### Problem → solution

| Buyer pain | Industry default | Webhook Mesh |
|------------|------------------|--------------|
| Double webhook → double charge | Best-effort dedupe | Redis SETNX + WAL before 200 |
| Multi-instance dedupe fails | In-memory | Redis fail-closed CAS |
| No audit | App logs | Genesis ledger + export |

### Competitive comparison

| Capability | Stripe idempotency | Custom middleware | **Webhook Mesh** |
|------------|-------------------|-------------------|------------------|
| WAL before provider ack | No | Rare | **Yes** |
| Multi-instance dedupe | Stripe-only | DIY | **Redis Lua CAS** |
| Stripe / Shopify routes | Stripe-native | DIY | **Built-in** |
| Offline verify | No | No | **verify-bundle** |

**Win when:** idempotent ingress + audit proof.  
**Lose when:** Kafka-scale streaming or Stripe Connect dashboard.

**Demo:** `./scripts/demo_webhook_mesh.sh` · **Spec:** [WEBHOOK_MESH_SALES_TECH_SPEC.md](WEBHOOK_MESH_SALES_TECH_SPEC.md)

### Completion status

| Layer | Status | Detail |
|-------|--------|--------|
| **Institutional gold** | ✅ | HMAC fail-closed; Redis idempotency CAS; WAL before HTTP 200; genesis cold-path ledger |
| **Production deploy** | 🟡 | Stripe + Shopify routes ✅; **background queue** — tasks lost on crash unless Redis Stream configured (documented) |
| **Workflow UI** | 🔲 | CLI + `serve` only |
| **Commercial pack** | ✅ | `demo-sign` for Stripe/Shopify; buyer sheet, sales spec |
| **GTM** | 🔲 | No paying billing-platform tenants |
| **Explicit non-goals** | — | Kafka-scale event bus · Stripe Connect dashboard |

**CI proof:** `webhook_mesh` in rigorous E2E — **PASSED**

---

## 6 — Ad Guard

**One job:** Marketing API **spend kill** at the boundary — Google/Meta parsers, Z-score kill, genesis gate audit.

**Pitch:** *Stop runaway Google/Meta API spend before finance sees the bill.*

### License economics

| Band | £/mo | Typical buyer |
|------|------|---------------|
| Single instance | £300–£500 | Agency / growth team |
| Enterprise + Redis | £500–£800 | Marketing finance oversight |

| Scenario | Tenants | Avg £/mo | ARR | Why it's realistic |
|----------|---------|----------|-----|-------------------|
| Y1 conservative | 3–5 | £450 | **£16k–£27k** | One agency misconfig story closes a deal |
| Y1 stretch | 8–10 | £600 | **£58k–£72k** | Stacks with NeMo upstream in enterprise marketing |
| Y2 capable | 15–20 | £650 | **£117k–£156k** | Spend kill ROI is measurable in £ |

**Why this price vs market:** Finance alerts are post-hoc. DSP caps are placement-specific. **Pre-forward Z-score kill + audit** is a niche neither finance nor ad tech owns — price like infra, not % of media.

### Problem → solution

| Buyer pain | Industry default | Ad Guard |
|------------|------------------|----------|
| Runaway API spend | Post-hoc finance alert | Z-score kill at boundary |
| No spend-layer proof | DSP dashboards | Genesis chain per gate |
| Payload parsing | Manual | Built-in `bidMicros` / `daily_budget` |

### Competitive comparison

| Capability | Finance alerts | DSP native caps | **Ad Guard** |
|------------|----------------|-----------------|--------------|
| API-boundary kill | Post-hoc | Partial | **Pre-forward Z-score** |
| Google/Meta parsers | Manual | N/A | **Built-in** |
| Every gate logged | No | No | **approve/reject/kill** |
| Offline verify | No | No | **verify-bundle** |

**Stack:** NeMo/Bedrock (safety) → **Ad Guard** (spend) → DSP + DV/IAS (placement)

**Demo:** `./scripts/demo_ad_guard.sh` · **Spec:** [AD_GUARD_SALES_TECH_SPEC.md](AD_GUARD_SALES_TECH_SPEC.md)

### Completion status

| Layer | Status | Detail |
|-------|--------|--------|
| **Institutional gold** | ✅ | All gate outcomes logged; Z-score kill; Google/Meta parsers; Redis idempotency fail-closed |
| **Production deploy** | 🟡 | Live `httpx` via `AD_GUARD_UPSTREAM_BASE`; NeMo/creative approval headers optional; Redis for multi-instance |
| **Workflow UI** | 🔲 | `ad-guard serve` HTTP gateway — no guided browser console |
| **Commercial pack** | ✅ | Buyer sheet, sales spec, stack-position docs (NeMo → Ad Guard → DSP) |
| **GTM** | 🔲 | No agency / marketing-finance logos |
| **Explicit non-goals** | — | Sub-5ms RTB · DSP / campaign UI · DV/IAS placement |

**CI proof:** `ad_guard` in rigorous E2E — **PASSED**

---

## 7 — Health Telemetry

**One job:** Device batch **tamper evidence** — schema + sequence gate + optional WAL ingress, HIPAA diligence pack, not FDA cert.

**Pitch:** *Prove telemetry batches weren't altered — without buying an EMR.*

### License economics

| Band | £/mo | Typical buyer |
|------|------|---------------|
| License (Y1) | £5k–£15k one-time + £500/mo | Ward pilot / RPM vendor |
| Effective monthly | £900–£1,750 | Amortised over 12 mo + maintenance |

| Scenario | Pilots | Effective £/mo | ARR | Why it's realistic |
|----------|--------|----------------|-----|-------------------|
| Y1 conservative | 2–3 | £1,200 | **£29k–£43k** | Hospital sales are slow; license-heavy fits procurement |
| Y1 stretch | 5–6 | £1,400 | **£84k–£101k** | One NHS-adjacent anchor + digital health cluster |
| Y2 capable | 10–15 | £1,500 | **£180k–£270k** | Expansion wards + second RPM vendor |

**Why this price vs market:** Cloud IoT hub is consumption-priced with vendor trust. EMR integration is £100k+ projects. **£10k–£20k Y1 all-in** is credible for tamper evidence + HIPAA pack without device certification scope.

### Problem → solution

| Buyer pain | Industry default | Health Telemetry |
|------------|------------------|------------------|
| Vendor trust for integrity | “Trust AWS” | Genesis chain, buyer verifies |
| Spreadsheet exports | Editable CSV | Deterministic tar + SHA256 |
| Device clock drift / replay | NTP trust only | Lamport per batch + **per-device `seq` gate** |
| PHI in auditor export | Full payload | **`--observation-lane`** summaries |

### Competitive comparison

| Capability | Cloud IoT hub | Spreadsheet export | **Health Telemetry** |
|------------|---------------|-------------------|---------------------|
| Tamper-evident chain | Vendor trust | None | **Genesis hash chain** |
| Offline verify | No | No | **verify-bundle** |
| HIPAA diligence pack | Vendor cert | No | **Template + playbook** |
| FDA / device cert | Sometimes | N/A | **Explicitly out of scope** |

**Win when:** tamper-evident log + HIPAA docs, not a certified device.  
**Lose when:** FDA/UKCA, EMR/FHIR, real-time clinical UI.

**Demo:** `./scripts/demo_health_telemetry.sh` · **Spec:** [HEALTH_TELEMETRY_SALES_TECH_SPEC.md](HEALTH_TELEMETRY_SALES_TECH_SPEC.md)

### Completion status

| Layer | Status | Detail |
|-------|--------|--------|
| **Institutional gold** | ✅ | Schema + `seq` gate + F7 coverage; WAL ingress; observation-lane export; rigorous E2E |
| **Production deploy** | 🟡 | Air-gap VPC ✅; HIPAA diligence **template** + hospital pilot playbook — not a signed BAA or ward go-live |
| **Workflow UI** | 🔲 | CLI ingest only — no clinical dashboard |
| **Commercial pack** | ✅ | `HEALTH_TELEMETRY_HIPAA_PACK.md` · `HEALTH_TELEMETRY_HOSPITAL_PILOT.md` |
| **GTM** | 🔲 | Long hospital sales cycle; no paid pilots signed |
| **Explicit non-goals** | — | FDA / UKCA / DTAC · EMR / FHIR · real-time clinical alerting · cloud IoT device management |

**CI proof:** `health_telemetry` in rigorous E2E — **PASSED**

---

## 8 — ModelGovernor

Two surfaces — sell separately in diligence:

| Surface | Buyer | Demo |
|---------|-------|------|
| **8a Lifecycle CLI** | Model risk, MLOps, regulated lending | `./scripts/demo_model_governor.sh` |
| **8b LLM spend plane** | Platform eng, FinOps, AI gateway buyers | `make demo-gold` — see [DEMO_GOLD.md](DEMO_GOLD.md) |

**Pitch (lifecycle):** *Prove which model version was approved for production on date X.*  
**Pitch (spend plane):** *LiteLLM and Portkey govern traffic; ModelGovernor governs money.*

---

### 8a — Lifecycle CLI (#8 portfolio SKU)

#### License economics

| Band | £/mo | Typical buyer |
|------|------|---------------|
| Standard | £400–£700 | ML platform team |
| Regulated / MRM | £700–£1,000 | Lending / insurtech with auditor requirement |

| Scenario | Tenants | Avg £/mo | ARR | Why it's realistic |
|----------|---------|----------|-----|-------------------|
| Y1 conservative | 3–5 | £550 | **£20k–£33k** | SR 11-7 adjacent buyers exist; sales cycle matches compliance logger |
| Y1 stretch | 8–10 | £750 | **£72k–£90k** | One regulated lender anchor |
| Y2 capable | 12–18 | £800 | **£115k–£173k** | Pairs naturally with Compliance Logger in same holding co |

#### Competitive comparison (lifecycle)

| Capability | MLflow Registry | GRC SaaS | **ModelGovernor CLI** |
|------------|-----------------|----------|----------------------|
| Model snapshot contract | Tags/params | Custom fields | **First-class** |
| Approve/deploy audit | Version history | Case workflow | **Genesis per event** |
| Offline verify | Needs server | No | **verify-bundle** |
| Drift as sealed event | Metrics only | Ticket | **`drift_alert` on chain** |

**Win when:** model-specific governance proof without full MLOps lock-in.  
**Lose when:** MLflow UI, experiment tracking, hosted serving.

**Spec:** [MODEL_GOVERNOR_SALES_TECH_SPEC.md](MODEL_GOVERNOR_SALES_TECH_SPEC.md)

#### Completion status (8a lifecycle)

| Layer | Status | Detail |
|-------|--------|--------|
| **Institutional gold** | ✅ | `register` / `approve` / `deploy` / `retire` / `drift_alert`; model snapshot contract; F7 on snapshot |
| **Production deploy** | ✅ | Air-gap SQLite + WAL; same spine as portfolio |
| **Workflow UI** | 🔲 | CLI only |
| **Commercial pack** | ✅ | Buyer sheet, sales spec, `demo_model_governor.sh` |
| **GTM** | 🔲 | No MRM / lending logos |
| **Explicit non-goals** | — | MLflow UI · experiment tracking · hosted model serving · real-time drift monitoring service |

**CI proof:** `model_governor` in rigorous E2E — **PASSED**

---

### 8b — LLM spend control plane

#### License economics

| Band | £/mo | Typical buyer |
|------|------|---------------|
| VPC pilot | £1,500–£2,500 | Platform team replacing LiteLLM budgets |
| Production + reconciler | £2,500–£5,000 | Enterprise AI gateway + FinOps sponsor |

| Scenario | Tenants | Avg £/mo | ARR | Why it's realistic |
|----------|---------|----------|-----|-------------------|
| Y1 conservative | 1–2 pilots | £2,000 | **£24k–£48k** | Pre-revenue — paid pilot is the milestone, not volume |
| Y1 stretch | 3–5 | £3,000 | **£108k–£180k** | One enterprise replaces internal LiteLLM + finance signs off |
| Y2 capable | 6–10 | £3,500 | **£252k–£420k** | Land with gateway; expand with wallet + reconciler modules |

**Why this price vs market:** LiteLLM enterprise and Portkey are **usage- and seat-scaled** — $50k–$150k+ ACV at scale. You price **below** full gateway suites but **above** observability-only tools because **reserve → settle → drift lockout** is finance infrastructure, not logging.

#### Competitive comparison (spend plane)

| Category | Examples | They do well | They usually don't |
|----------|----------|--------------|-------------------|
| AI gateway / proxy | LiteLLM, Portkey, Kong AI, OpenRouter | Route, keys, fallbacks, budgets | Postgres ledger, reserve-before-dispatch, drift → wallet lockout, reconciler |
| LLM observability | Helicone, LangSmith, Arize | Traces, evals | Block spend before inference; authoritative settlement |
| Cloud FinOps | Kubecost, Cloudability | Infra chargeback | Per-request LLM governance at gateway |

| vs comp | Same | Different (why you win) |
|---------|------|-------------------------|
| **LiteLLM** | OpenAI API, multi-provider, budgets | Budgets are limits/tracking — not append-only reserve → settle → drift lockout |
| **Portkey** | Enterprise gateway, governance, routing | Deeper **money correctness** (wallet, reconciler, hash-chain audit) |
| **Helicone** | Gateway + observability | Observability-first — not wallet control plane |
| **Kubecost** | Stop runaway spend mindset | LLM token path, not K8s infra |

**Canonical demo:**

```bash
make demo-gold-up
make demo-gold          # 11 steps — drift lockout step 10
make demo-gold-reset    # before rerun
make demo-gold-down
```

**Deep comps:** [MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md](MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md) (exit framing in Value today section below)

#### Completion status (8b spend plane)

| Layer | Status | Detail |
|-------|--------|--------|
| **Canonical demo** | ✅ | `make demo-gold` — 11 steps; drift lockout step 10; `docker-compose.demo.yml` stack (gateway + sidecar + reconciler) |
| **Institutional CI** | 🟡 | **Not** in `instpp_rigorous_test.sh` path — proof is compose demo, not CLI E2E |
| **Production deploy** | 🟡 | Reserve → dispatch → settle + reconciler in demo stack; **K8s/GitOps manifests** not in portfolio CI |
| **Commercial pack** | ✅ | `DEMO_GOLD.md`, positioning doc, LiteLLM/Portkey comp map |
| **GTM** | 🔲 | Pre-revenue; no paid pilot replacing LiteLLM budgets |
| **Explicit non-goals** | — | “Another observability dashboard” · traffic-only proxy without wallet semantics |

---

## Portfolio revenue — how the numbers stack

| Motion | Y1 conservative | Y1 stretch | What has to be true |
|--------|-----------------|------------|---------------------|
| **Single SKU focus** (e.g. Proxy-Risk only) | £15k–£30k ARR | £50k–£100k ARR | One vertical, 3–10 tenants |
| **2–3 SKU bundle** (e.g. #1 + #2 + #5) | £40k–£80k ARR | £100k–£200k ARR | Same buyer holding co — spine discount applies |
| **ModelGovernor spend plane** | £24k–£48k ARR | £108k–£180k ARR | Paid pilot replaces LiteLLM budgets |
| **Full portfolio** (unrealistic single GTM) | £120k–£350k | £280k–£700k | Integrator / PE roll-up buys IP + services |

**First £50k ARR** (any SKU) changes buyer conversations from IP-sale to **3–8× ARR** infra multiples — see Value today.

---

## Diligence (15 minutes)

```bash
pip install -e ".[dev,instpp]"
./scripts/instpp_smoke_test.sh          # 91 tests
./scripts/instpp_rigorous_test.sh       # 8/8 E2E
./scripts/demo_instpp.sh                # all CLI demos
make demo-gold-up && make demo-gold       # ModelGovernor spend plane
```

**Evidence:** [BUYER_EVIDENCE_PACK.md](BUYER_EVIDENCE_PACK.md) · [SOC2_VPC_DILIGENCE_PACK.md](SOC2_VPC_DILIGENCE_PACK.md)

---

## Pilot ladder

| Stage | Duration | Deliverable | Buyer pays |
|-------|----------|-------------|------------|
| Dry-run | 1 meeting | Demo + `verify-bundle` on sample tarball | Time only |
| Shadow | 2–4 weeks | VPC deploy, shadow mode (#2, #6) or read-only (#3) | Eng time |
| Live pilot | 4–8 weeks | Single tenant, one route/feed/ward | £2k–£8k or LOI |
| Production | — | Annual license + 15–20% maintenance | Per tables above |

---

# Value today

**Purpose:** Honest rough value of **code + IP + diligence package** as it sits **pre-revenue** (June 2026).  
**Not:** A formal 409A, investment memo, or guarantee of sale price.

### Completion vs value (how to read this)

| Completion state | What it means for value |
|------------------|-------------------------|
| **8/8 Gold CLI** in rigorous CI | IP floor is **real** — not slideware; auditor dry-run works today |
| **🟡 Production** on several SKUs | Buyer assumes SOW for Redis, feeds, hospital pilot — not a rewrite |
| **🔲 GTM everywhere** | Valuation is **IP / replacement cost**, not ARR multiples — until first £50k ARR |
| **8b spend plane** demo gold but not in CI | Strategic premium is **buyer-specific** — see #8b row below |

---

## IP value by product (standalone)

| # | Product | Completion | Standalone IP range | Notes |
|---|---------|------------|---------------------|-------|
| 1 | Compliance Logger | **Gold** | **£25k–£75k** | ~15% shared spine |
| 2 | Proxy-Risk | **Gold** | **£30k–£90k** | ~15% shared spine |
| 3 | Alt-Data | **Gold** | **£20k–£50k** | ~12% shared spine |
| 4 | AI Kit | **Gold** | **£10k–£30k** | ~10% shared spine |
| 5 | Webhook Mesh | **Gold** | **£15k–£40k** | ~12% shared spine |
| 6 | Ad Guard | **Gold** | **£15k–£45k** | ~12% shared spine |
| 7 | Health Telemetry | **Gold** | **£30k–£80k** | ~12% shared spine |
| 8a | ModelGovernor (lifecycle CLI) | **Gold** | **£25k–£70k** | ~12% shared spine |
| 8b | ModelGovernor (LLM spend plane) | **Demo gold** | **£2M–£7M** strategic exit band | Not lifecycle SKU alone — see positioning doc |
| | **Full portfolio (one spine)** | **8/8 CI Gold** | **£70k–£150k** | $89k–$190k at ~1.27 |

---

## What drives value up / down

| Driver (↑) | Dragger (↓) |
|------------|-------------|
| Offline `verify-bundle` — rare auditor wedge | No revenue / no LOI — IP multiples only |
| 91 tests + rigorous E2E 8/8 | Shared monorepo sports adjacency |
| Sales tech specs + evidence pack (all 8) | No SOC 2 Type II |
| Air-gap default for regulated buyers | Single maintainer bus factor |
| Separate SKUs + clean extract path | Python hot path vs Go/Rust for quant |

---

## Value inflection points

| Milestone | Effect on value |
|-----------|-----------------|
| First £50k ARR (any SKU) | Reframe to **£280k–£400k** ecosystem (3–7× ARR) |
| Pilot LOI from tier-1 fintech | **+£25k–£50k** to IP floor |
| Paid ModelGovernor spend pilot (£50k+) | Moves #8b toward strategic comp narrative |
| Two bidders + data room | ModelGovernor platform **£4.5M–£7M** headline (see positioning doc) |

---

## Deal structures (pre-revenue)

| Structure | Typical range |
|-----------|---------------|
| IP license + source (perpetual, one tenant) | £40k–£80k |
| IP sale (exclusive, one product) | £50k–£100k |
| Acqui-hire (code + 1–2 engineers) | £80k–£200k total |
| Spine bundle discount | 15–25% off sum of singles |

---

## Related valuation documents

| Doc | Scope |
|-----|-------|
| [INST_PLUS_PRE_REV_VALUATION.md](INST_PLUS_PRE_REV_VALUATION.md) | Full methodology, replacement cost, comps |
| [MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md](MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md) | LLM spend plane comps, UK exit scenarios |
| [PORTFOLIO_SALES_SHEET.md](PORTFOLIO_SALES_SHEET.md) | Short commercial matrix |

---

*Revenue tables above are forward-looking license capability. Value today is backward-looking IP floor. Pre-revenue code value ≠ ARR.*
