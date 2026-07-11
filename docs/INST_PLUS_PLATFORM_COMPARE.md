# Institutional++ — Platform Comparison Deep Dive

**Purpose:** Gauge Inst++ capabilities against adjacent platforms using **factual, evidence-backed** criteria, plus **public market pricing** for comparables (2025–2026). Inst++ pricing is intentionally omitted — see commercial docs separately.  
**Scope:** SKU / Inst++ infrastructure only.  
**Evidence source:** In-repo tests, `verify-bundle`, rigorous CI logs, and public vendor pricing pages (cited below).  
**Date:** July 2026

> **Inst++ full tech/sales (no prices):** [PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md](PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md)  
> **Inst++ evidence index:** [PORTFOLIO_EVIDENCE_SHEET.md](PORTFOLIO_EVIDENCE_SHEET.md)

---

## How to read this document

| Symbol | Meaning |
|--------|---------|
| **Proven (repo)** | Capability exercised in Inst++ tests, demos, or rigorous CI with committed log artifacts |
| **Typical (market)** | Common capability in the named platform category based on public docs — not a claim they lack other features |
| **Gap** | Inst++ does not aim to replace this category's full product surface |
| **Partial** | Overlap exists but deployment model or depth differs |

Comparable platforms are grouped by **job-to-be-done**, not by company size. Inst++ is a **VPC-deployable audit spine** with twelve focused SKUs; most comparables are **single-category SaaS or OSS servers**.

---

## Executive positioning

| Dimension | Inst++ (this repo) | Typical comparable stack |
|-----------|-------------------|--------------------------|
| Deployment | Air-gap VPC, SQLite default, optional Redis/Postgres | SaaS control plane or cloud-managed |
| Proof model | Offline `verify-bundle` on every SKU | Vendor dashboard, API audit APIs, or DB replication |
| Scope | 12 gate products + shared `inst_spine` | One product per vendor (webhooks OR registry OR spend) |
| Multi-SKU chain | Proxy → Drift → Spend → Agent on one genesis contract | Integration glue between vendors |
| Test evidence | 219+ smoke tests, 45 rigorous sections, docker-extended zero-skip | Vendor SOC2 PDFs; buyer runs own eval |

**Inst++ sweet spot:** Buyers who must **prove gate decisions offline** (regulators, model risk, SOC2, agent governance) and want **one cryptographic contract** across compliance, API control, webhooks, ML lifecycle, and spend — without calling home.

**Not competing on:** Full GRC workflow suites, payment processing, generic observability APM, or managed webhook SaaS at infinite scale.

---

## Market pricing gauge (2025–2026 public sources)

**Disclaimer:** Comparable prices are from vendor list pages, AWS Marketplace, and third-party benchmark reports as of mid-2026. Enterprise deals are almost always discounted; self-hosted OSS has **$0 license** but real **TCO** (infra + DevOps). Figures are **USD** unless noted. Verify live before procurement.

### Quick reference — what the market charges

| Category | Vendor | Public entry | Mid-market typical | Enterprise / custom | Billing model |
|----------|--------|--------------|-------------------|---------------------|---------------|
| Inbound webhooks | **Hookdeck** | $0 (10k events/mo) | $39/mo + ~$3–33/100k events | $499/mo Growth; Enterprise custom | Base + metered events |
| Outbound webhooks | **Svix** | $0 (50k msgs/mo) | $490/mo Pro | Custom; $0.0001/msg overage | Base + messages |
| API gateway | **Kong Konnect Plus** | ~$105/mo per gateway service | $50k–$120k/yr (Vendr benchmarks) | $150k–$300k+/yr Enterprise | Per service + per-million requests |
| API gateway | **AWS API Gateway** | Pay-per-request | Varies by volume | Enterprise support separate | Per million API calls |
| GRC / IRM | **ServiceNow GRC** | N/A (quote only) | $85k–$365k/yr (3 modules, Pro) | $780k–$2.2M+ Fortune-scale | Per module + scope band |
| GRC tier-2 | **OneTrust / MetricStream** | N/A | $75k–$250k/yr | $250k–$500k+ | Module + users |
| Immutable ledger | **AWS QLDB** | **Discontinued Jul 2025** | Was ~$0.70/M writes | Migrated to Aurora patterns | Was pay-per-IO |
| Immutable ledger | **immudb** | OSS free | Cloud/hosted varies | Enterprise support custom | OSS + optional cloud |
| ML registry | **MLflow** | OSS free | Databricks-hosted extra | Enterprise Databricks | Platform bundle |
| Drift / ML observability | **Evidently** | OSS free (Apache 2.0) | Evidently Cloud (contact) | Enterprise self-hosted | OSS + commercial platform |
| Drift / AI observability | **Fiddler** | Free guardrails tier | $0.002/trace Developer | ~$24k/yr AWS Marketplace Lite; Enterprise custom | Per trace / custom |
| LLM observability | **Langfuse** | $0 Hobby (50k units) | $29 Core; $199 Pro | $2,499/mo Enterprise base | Units (traces+spans+scores) |
| LLM observability | **LangSmith** | $0 (5k traces, 1 seat) | $39/seat/mo + $2.50/1k traces | Enterprise custom | Per seat + traces |
| LLM gateway | **LiteLLM** | OSS free | ~$250/mo Enterprise Basic (reports) | ~$30k/yr Premium (reports) | Custom quote + infra TCO |
| ETL | **Fivetran** | Limited free | $1k–$5k+/mo typical connectors | Enterprise custom | Per connector MAR |
| IoT ingress | **AWS IoT Core** | Pay-per-message | Scales with devices | Enterprise support | Per million messages |

**Sources (verify live):** [hookdeck.com/pricing](https://hookdeck.com/pricing) · [svix.com/pricing](https://www.svix.com/pricing) · [konghq.com/pricing](https://konghq.com/pricing) · [langfuse.com/pricing](https://langfuse.com/pricing) · [langchain.com/pricing](https://www.langchain.com/pricing) · [fiddler.ai/pricing](https://www.fiddler.ai/pricing) · [docs.litellm.ai/docs/enterprise](https://docs.litellm.ai/docs/enterprise) · vendor benchmark reports (ServiceNow GRC, Kong TCO)

---

### Category pricing deep dives

#### Webhooks — Hookdeck vs Svix (inbound vs outbound)

| Plan | Hookdeck (inbound) | Svix (outbound + ingest) |
|------|-------------------|--------------------------|
| Free | $0 — 10k events/mo, 3-day retention, 1 user | $0 — 50k messages/mo, 50 msg/s, 30-day retention |
| Team / Pro | **$39/mo** + metered events ($0.33–$3.00 per 100k) | **$490/mo** — 50k included, 400 msg/s, 90-day retention |
| Growth / Enterprise | **$499/mo** — SLAs, SSO, 30-day retention | Enterprise custom — 99.999% SLA, on-prem options |
| Static IP add-on | +$100/mo (Hookdeck) | Static IPs on Pro (Svix) |

**Value gauge:** For a SaaS doing **500k inbound billing webhooks/month**, Hookdeck Team often lands **~$40–55/mo** (base + metered). Svix at **1M outbound deliveries/month** is roughly **$490 base + ~$95 overage** ≈ **$585/mo** — order of magnitude **$5k–7k/year** for serious webhook infra, before Enterprise.

**Inst++ (#5 + #10) value angle:** VPC perpetual deploy — no per-message meter. Buyer pays **hosting + maintenance**, not **$0.0001/message** at scale. Trade-off: no managed portal, buyer operates Redis/compose.

---

#### API gateway — Kong vs DIY proxy

| Cost line | Kong Konnect Plus (public + benchmarks) | Kong Enterprise (benchmarks) | Inst++ Proxy-Risk (#2) |
|-----------|----------------------------------------|------------------------------|------------------------|
| License | ~$105/mo per gateway service + $200 per extra 1M requests/mo | $30k–$50k/yr small; $150k–$400k/yr large | **No per-request meter in repo** |
| Infra | Dedicated gateway ~$720/mo cited in AI routing guides | Self-hosted nodes + support tier | SQLite/Redis VPC |
| DevOps TCO | 0.5–2 FTE ($60k–$240k/yr cited) | Same + PS $40k–$80k | Lower surface — CLI + K8s init |
| Audit proof | Enterprise audit logs (SSO-gated) | CloudTrail partial | **Genesis per gate + verify-bundle** |

**Value gauge:** Mid-market Kong **year-1 TCO** often **$145k–$350k** (license + infra + DevOps per Zuplo/Vendr 2026 analyses). Inst++ targets buyers who need **Z-score kill + offline proof** at **infra license economics**, not **full API lifecycle platform**.

---

#### GRC vs tamper-evident decision ledger

| Tier | Typical annual spend (USD) | What you get |
|------|---------------------------|--------------|
| Point compliance tools | $5k–$25k | Narrow attestations |
| Mid-market GRC (LogicGate, Riskonnect) | $15k–$75k | Risk + policy modules |
| Enterprise GRC (ServiceNow IRM) | $180k–$500k+ | Workflow, attestations, audit mgmt |
| Global enterprise GRC | $580k–$2.2M+ post-discount | Full IRM + VRM + resilience |

**Value gauge:** ServiceNow **Policy & Compliance** alone is often **$45k–$140k/yr** list band per module (Reveal Compliance 2026 planning ranges). Inst++ Compliance Logger (#1) is **not** a GRC replacement — it is **10–20% of GRC ACV** for the **cryptographic decision spine only** when buyers already have workflow elsewhere.

---

#### LLM observability — Langfuse vs LangSmith

| Vendor | Entry paid | Mid-volume example | Enterprise |
|--------|-----------|-------------------|------------|
| **Langfuse** | $29/mo Core (100k units) | 500k units/mo ≈ **$231/mo** on Core | $2,499/mo base + graduated overage |
| **LangSmith** | $39/seat/mo (10k traces) | 8 seats + 500k traces/mo ≈ **$1,300+/mo** | Custom |

**Value gauge:** Observability is **usage- and seat-compounding**. LangSmith **seat tax** ($39 × team size) dominates at 10+ engineers. Langfuse **unit overage** dominates at high trace volume. Neither provides **offline verify-bundle** or **pre-execution tool authorization** — different job from Inst++ #4 / #12.

---

#### LLM gateway & spend — LiteLLM vs Spend Guard

| | LiteLLM OSS | LiteLLM Enterprise (reports) | Inst++ Spend Guard (#11) |
|--|-------------|------------------------------|--------------------------|
| License | $0 | ~$250/mo Basic; ~$30k/yr Premium | VPC deploy (commercial separate) |
| Budgets | Virtual keys, team budgets | SSO, RBAC, audit logs, SLA | **Reserve → settle → drift lockout** |
| TCO at scale | $2k–$3.5k/mo all-in (infra + labor cited) | + license | Air-gap SQLite/Postgres wallet |
| Proof | Metrics / logs | Enterprise audit logs | **Genesis spend events + verify-bundle** |

**Value gauge:** LiteLLM wins **routing breadth** (100+ providers) at **$0 OSS**. Enterprise adds **$3k–$36k/yr** for governance features. Spend Guard competes on **money correctness** (hold/settle/lockout), not **provider catalog** — complementary in many architectures.

---

#### Drift & model risk — Evidently vs Fiddler vs Drift Gate

| Vendor | Entry | Mid | Enterprise |
|--------|-------|-----|------------|
| **Evidently OSS** | $0 (Apache 2.0) | Self-host infra only | Evidently Cloud / Enterprise (quote) |
| **Fiddler** | Free guardrails | **$0.002/trace** Developer | **~$24k/yr** AWS Marketplace Lite (1 model, 0.5GB/mo); Enterprise custom |
| **Inst++ Drift Gate** | VPC deploy | PSI/KS **inline enforce** | Offline verify-bundle |

**Value gauge:** Fiddler at **1M traces/month** on Developer ≈ **$2,000/mo** metered. Evidently OSS is **free** but **dashboard/enforce** is DIY. Drift Gate value is **blocking traffic** with **genesis audit**, not **DS exploration UI**.

---

### Composite stack TCO — buy vs build vs Inst++

Illustrative **mid-market fintech** needing: audit trail, outbound API control, webhook idempotency, model approval, drift enforce, LLM spend guard, agent tool auth.

| Approach | Typical vendors | Indicative annual spend (USD) | Offline single manifest |
|----------|----------------|------------------------------|-------------------------|
| **Best-of-breed SaaS** | ServiceNow PCM + Kong Enterprise + Hookdeck Growth + MLflow/Databricks + Fiddler + LangSmith + LiteLLM Ent | **$400k–$900k+/yr** licenses alone (before PS) | No |
| **Lean SaaS** | Point GRC + Hookdeck Team + Langfuse Pro + LiteLLM OSS + Evidently OSS | **$50k–$150k/yr** + engineering glue | No |
| **Inst++ VPC portfolio** | 12 SKUs on `inst_spine` | **License economics separate** — hosting + 1 FTE ops typical | **Yes — `PORTFOLIO_MANIFEST.json`** |

**Value gauge (qualitative):**

| Buyer priority | Market stack wins | Inst++ wins |
|----------------|-------------------|-------------|
| Fastest time-to-dashboard | Langfuse, Hookdeck, Fiddler SaaS | — |
| Lowest year-1 cash (OSS) | LiteLLM + Evidently + immudb DIY | Partial — VPC license + ops |
| Auditor offline proof | Weak across SaaS | **verify-bundle 12/12** |
| Regulated agent + spend + model | 4–6 vendors + integration risk | **#8 + #9 + #11 + #12 one spine** |
| Per-message / per-trace meter at scale | SaaS can get expensive | **Flat VPC** favorable at high volume |

---

### Inst++ positioning vs market spend (no Inst++ prices)

Use this table in sales conversations — **compare buyer's current vendor line items** to **capability overlap**, not dollar-for-dollar SKU mapping.

| Inst++ SKU | Closest market comp | Market $ band (indicative) | Inst++ proof advantage | Market comp advantage |
|------------|--------------------|-----------------------------|------------------------|----------------------|
| #1 Compliance Logger | ServiceNow PCM / immudb | $45k–$140k/yr module vs OSS | Offline decision-event verify | Workflow / ecosystem |
| #2 Proxy-Risk | Kong / Apigee | $50k–$300k+/yr | Z-score kill + genesis audit | Plugins, scale, portal |
| #5 Webhook Mesh | Hookdeck / Svix | $0–$6k/yr SMB; $6k–$50k+ at scale | WAL-before-ack + verify-bundle | Managed reliability UI |
| #8 ModelGovernor | MLflow + GRC | $20k–$200k+ depending stack | Approve/deploy chain proof | Experiment UI, hosting |
| #9 Drift Gate | Fiddler / Evidently | $0 OSS – $24k+/yr | Inline enforce + audit | Dashboards, judges |
| #11 Spend Guard | LiteLLM Enterprise | $3k–$36k/yr + TCO | Reserve/settle/lockout | 100+ provider routes |
| #12 Agent Ledger | LangSmith + Oso | $39/seat/mo + traces | Pre-exec authorization proof | Trace UI, policy DSL |

---

## Category 1 — Tamper-evident audit & compliance ledger

**Inst++ SKU:** #1 Compliance Logger  
**Comparables:** immudb, Trillian/Chronicle, AWS QLDB, traditional GRC vaults (ServiceNow GRC, Archer)

| Capability | Inst++ | immudb / Trillian | QLDB | Enterprise GRC |
|------------|--------|-------------------|------|----------------|
| Append-only tamper evidence | **Proven (repo)** — genesis chain + export | **Typical** — Merkle / immutability | **Typical** — journal | **Typical** — workflow + attachments |
| Offline auditor verify (no vendor) | **Proven (repo)** — `verify-bundle` | **Partial** — client verify APIs | **Partial** — AWS API needed | **Gap** — exports are documents |
| Decision-event schema (approve/deny) | **Proven (repo)** | **Gap** — general KV | **Gap** | **Typical** — case management |
| mTLS ingest | **Proven (repo)** — phase 3 rigorous | **Typical** — TLS | **Typical** | **Typical** |
| Epoch roots in export | **Proven (repo)** | **Partial** | **Partial** | **Gap** |
| Per-seat GRC workflows | **Gap** | **Gap** | **Gap** | **Typical** |

**Gauge:** Inst++ is **narrower but deeper on cryptographic export** than GRC suites; **more opinionated on decision events** than immudb/QLDB general ledgers.

---

## Category 2 — Outbound API gateway & risk firewall

**Inst++ SKU:** #2 Proxy-Risk (+ #9 Drift Gate integration)  
**Comparables:** Kong, Apigee, AWS API Gateway, Solo Gloo

| Capability | Inst++ | Kong / Apigee | AWS API GW |
|------------|--------|---------------|------------|
| Rate limit + circuit break | **Proven (repo)** | **Typical** | **Typical** |
| Idempotency dedupe | **Proven (repo)** | **Partial** — plugins | **Partial** |
| Z-score / statistical kill | **Proven (repo)** | **Gap** | **Gap** |
| Shadow vs live burn-in | **Proven (repo)** | **Partial** — canary | **Partial** |
| Genesis audit per gate outcome | **Proven (repo)** | **Gap** — access logs | **Partial** — CloudTrail |
| p99 &lt;10ms shadow path | **Proven (repo)** — industry gold tests | **Typical** at edge | **Typical** |
| Multi-tenant SaaS portal | **Gap** | **Typical** | **Typical** |

**Gauge:** Inst++ trades **portal breadth** for **fail-closed risk gates + offline proof** on the proxy path. Kong/Apigee win on **ecosystem plugins and scale**; Inst++ wins when **every reject must be export-verifiable**.

---

## Category 3 — Inbound webhooks & idempotency

**Inst++ SKUs:** #5 Webhook Mesh, #10 Webhook Replay  
**Comparables:** Svix, Hookdeck, Stripe webhook tooling (built-in), custom middleware

| Capability | Inst++ | Svix / Hookdeck | DIY middleware |
|------------|--------|-----------------|----------------|
| WAL before HTTP 200 | **Proven (repo)** | **Typical** — durability focus | **Partial** — varies |
| Redis cross-pod idempotency | **Proven (repo)** | **Typical** | **Partial** |
| HMAC fail-closed | **Proven (repo)** | **Typical** | **Partial** |
| Byte-identical replay (.wrcap) | **Proven (repo)** — #10 | **Partial** — event replay | **Gap** |
| Offline verify-bundle on ledger | **Proven (repo)** | **Gap** | **Gap** |
| Managed multi-tenant dashboard | **Gap** | **Typical** | **Gap** |
| XAUTOCLAIM consumer reclaim | **Proven (repo)** — phase 3 | **Typical** — queue products | **Partial** |

**Gauge:** Svix/Hookdeck optimize **delivery reliability and ops UX**; Inst++ optimizes **provable never-double-charge** with **forensic replay artifacts** auditors can verify offline.

---

## Category 4 — ML model registry & lifecycle

**Inst++ SKU:** #8 ModelGovernor  
**Comparables:** MLflow Model Registry, Weights & Biases Registry, SageMaker Model Registry, Verta

| Capability | Inst++ | MLflow / W&B | SageMaker |
|------------|--------|--------------|-----------|
| Register / approve / deploy / retire | **Proven (repo)** | **Typical** | **Typical** |
| Canonical artifact hash gate | **Proven (repo)** — `integrity.py` | **Partial** — checksums | **Partial** |
| Offline verify-bundle | **Proven (repo)** | **Gap** | **Gap** |
| Experiment tracking | **Gap** | **Typical** | **Typical** |
| Feature store | **Gap** | **Partial** | **Typical** |
| Drift enforce on inference path | **Partial** — via #9 Drift Gate | **Gap** — monitoring only | **Partial** |

**Gauge:** MLflow wins **experiment and artifact storage**; Inst++ wins **governance events on a tamper-evident chain** with **auditor-offline proof** — closer to **model risk management evidence** than MLOps convenience.

---

## Category 5 — Model drift detection & enforcement

**Inst++ SKU:** #9 Drift Gate  
**Comparables:** Evidently AI, Fiddler, Arize, WhyLabs

| Capability | Inst++ | Evidently / Fiddler | WhyLabs |
|------------|--------|---------------------|---------|
| PSI / KS per feature | **Proven (repo)** | **Typical** | **Typical** |
| Shadow → enforce (block traffic) | **Proven (repo)** | **Partial** — alerts common | **Partial** |
| Proxy hot-path integration | **Proven (repo)** — #2 | **Gap** — sidecar/batch | **Gap** |
| Genesis audit per evaluation | **Proven (repo)** | **Gap** | **Partial** |
| Dashboards & slicing UI | **Gap** | **Typical** | **Typical** |
| Offline verify-bundle | **Proven (repo)** | **Gap** | **Gap** |

**Gauge:** Monitoring vendors excel at **visualization and data science workflows**; Inst++ is an **inline enforce gate** with **cryptographic audit**, not a drift dashboard replacement.

---

## Category 6 — LLM / API spend control

**Inst++ SKU:** #11 Spend Guard  
**Comparables:** LiteLLM proxy + budget hooks, OpenAI org limits, cloud cost tools (CloudZero, Finout)

| Capability | Inst++ | LiteLLM | Cloud cost SaaS |
|------------|--------|---------|-----------------|
| Reserve before dispatch | **Proven (repo)** | **Partial** — budgets | **Gap** — post-hoc |
| Settle actual vs estimate | **Proven (repo)** | **Partial** | **Typical** — billing data |
| Drift lockout (wallet freeze) | **Proven (repo)** — demo-gold step 10 | **Gap** | **Gap** |
| OpenAI-compat gateway | **Proven (repo)** | **Typical** | **Gap** |
| Genesis spend events | **Proven (repo)** | **Gap** | **Gap** |
| Multi-cloud invoice aggregation | **Gap** | **Partial** | **Typical** |

**Gauge:** LiteLLM governs **routing and keys**; Inst++ governs **money with hold/settle semantics and provable lockout** — complementary, not interchangeable.

---

## Category 7 — AI agent tool governance

**Inst++ SKUs:** #12 Agent Ledger, #4 AI Kit  
**Comparables:** LangSmith tool policies, Bedrock Guardrails, custom policy engines, OPAL/Oso

| Capability | Inst++ | LangSmith / tracing | Oso / OPAL |
|------------|--------|---------------------|------------|
| Authorize before tool invoke | **Proven (repo)** | **Partial** — tracing | **Typical** |
| Deny / escalate fail-closed | **Proven (repo)** | **Partial** | **Typical** |
| Human attestation on escalation | **Proven (repo)** | **Gap** | **Partial** |
| Offline verify-bundle | **Proven (repo)** | **Gap** | **Gap** |
| Trace UI / prompt debugging | **Partial** — #4 trace ledger | **Typical** | **Gap** |
| step_fn contract tests | **Proven (repo)** — phase 3 | **Gap** | **Gap** |

**Gauge:** LangSmith wins **developer observability**; Inst++ wins **pre-execution policy proof** for regulated tool calls.

---

## Category 8 — Device / health telemetry ingress

**Inst++ SKU:** #7 Health Telemetry  
**Comparables:** AWS IoT Core, Azure IoT Hub, Timescale + custom ingestion

| Capability | Inst++ | Cloud IoT hubs |
|------------|--------|----------------|
| Per-device sequence gate | **Proven (repo)** | **Typical** |
| Device auth + fail-closed gaps | **Proven (repo)** | **Typical** |
| Observation-lane export verify | **Proven (repo)** | **Gap** |
| Global device fleet scale | **Partial** — VPC SQLite/Redis | **Typical** |
| FDA / medical certification | **Gap** — audit spine only | **Partial** — compliance programs |

**Gauge:** Inst++ is **audit ingress**, not a full IoT platform.

---

## Category 9 — Alt-data / feed reliability

**Inst++ SKU:** #3 Alt-Data  
**Comparables:** Airbyte, Fivetran, custom ETL, market-data vendor APIs

| Capability | Inst++ | Airbyte / Fivetran |
|------------|--------|-------------------|
| Per-poll proof bundle | **Proven (repo)** | **Gap** |
| Structural rescue golden path | **Proven (repo)** | **Partial** — error handling |
| Field coverage gate (≥85%) | **Proven (repo)** | **Partial** — schema tests |
| Connector catalog breadth | **Gap** | **Typical** |

**Gauge:** ETL vendors win **connector count**; Inst++ wins **provable poll cycles** for regulated telemetry.

---

## Category 10 — Ad spend anomaly guard

**Inst++ SKU:** #6 Ad Guard  
**Comparables:** Meta/Google native caps, internal FinOps scripts, Wiz-ish anomaly tools

| Capability | Inst++ | Platform native caps |
|------------|--------|----------------------|
| Z-score velocity kill | **Proven (repo)** | **Partial** — daily budgets |
| Per-campaign bucket | **Proven (repo)** | **Typical** |
| Creative body fuzz testing | **Proven (repo)** — phase 3 | **Gap** |
| Cross-channel ad analytics | **Gap** | **Typical** |

---

## Composite stack comparison

What a buyer might assemble vs Inst++ portfolio:

| Need | Multi-vendor stack | Inst++ portfolio |
|------|-------------------|------------------|
| Audit trail | GRC + SIEM export | #1 Compliance Logger |
| Outbound API risk | Kong + custom scripts | #2 Proxy-Risk |
| Webhook idempotency | Svix | #5 + #10 Webhook Mesh/Replay |
| Model approval | MLflow | #8 ModelGovernor |
| Drift block | Evidently + custom gate | #9 Drift Gate |
| LLM spend | LiteLLM | #11 Spend Guard |
| Agent tools | Oso + LangSmith | #12 + #4 Agent Ledger / AI Kit |
| **Offline single manifest** | **No standard** | **`PORTFOLIO_MANIFEST.json` + 12 verify-bundle** |
| **One genesis contract** | **Integration risk** | **`inst_spine` shared F1–F9** |

---

## Evidence Inst++ can show in diligence (not claims about rivals)

| Evidence artifact | What it demonstrates |
|-------------------|---------------------|
| `make plug` | 12/12 demos + offline verify in one command |
| `instpp_rigorous_latest_summary.json` | 45 E2E sections, forensic waves, skip honesty |
| `instpp_docker_extended_latest_summary.json` | Redis + Postgres live, zero-skip rigorous |
| `PORTFOLIO_MANIFEST.json` | Single manifest over 12 products |
| `soc2_evidence_latest.json` | VPC SOC2-oriented evidence collector output |
| `tests/test_phase3_buyer_depth.py` | Buyer-depth gates (mTLS, reclaim, hash, fuzz) |
| `make demo-gold` | Spend plane walkthrough with drift lockout |

---

## Where Inst++ is intentionally weaker

Honest gaps vs best-in-category SaaS:

1. **No managed multi-tenant console** — CLI + workflow UI (`:8790`), K8s manifests  
2. **No connector marketplace** — twelve focused products, not thousands of integrations  
3. **No DS drift dashboards** — enforce gate, not exploration UI  
4. **SQLite default** — Postgres/Redis are opt-in production profiles  
5. **No payment processing** — spend *governance*, not acquiring  
6. **Not a sports/trading product** — infrastructure SKUs only in this repo layer  

---

## Summary gauge

| Platform type | Inst++ relative position |
|---------------|-------------------------|
| GRC / audit vault | Stronger offline proof; weaker workflow |
| API gateway | Stronger risk audit; weaker plugin ecosystem |
| Webhook SaaS | Stronger forensic replay proof; weaker managed ops |
| MLOps registry | Stronger governance chain; weaker experiment UX |
| Drift monitoring | Stronger inline enforce; weaker visualization |
| LLM proxy | Stronger hold/settle/lockout; weaker routing catalog |
| Agent observability | Stronger pre-exec authorization proof; weaker trace UI |

**Bottom line:** Inst++ value is **portfolio-level cryptographic diligence** — one spine, twelve gates, reproducible CI and docker-extended logs — not winning every category feature-for-feature against specialized SaaS leaders.

---

## Related documents

| Doc | Purpose |
|-----|---------|
| [PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md](PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md) | Full tech + sales sheet (no Inst++ pricing) |
| [PORTFOLIO_EVIDENCE_SHEET.md](PORTFOLIO_EVIDENCE_SHEET.md) | Per-SKU proof commands and CI artifacts |
| [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) | Nine dimensions bar |
| [PORTFOLIO_TECH_SALES_SHEET.md](PORTFOLIO_TECH_SALES_SHEET.md) | Commercial economics (Inst++ pricing) |
| [docs/test_logs/README.md](test_logs/README.md) | Committed proof logs |
