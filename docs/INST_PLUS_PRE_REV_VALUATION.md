# Institutional Pre-Revenue Valuation — Full Portfolio (7 Products)

**Purpose:** Honest rough value range for the **code + IP + diligence package** before first revenue.  
**Not:** A formal 409A, investment memo, or guarantee of sale price.  
**Date:** June 2026 · Gold standard across all 7 products

---

## What is being valued

| Asset | Description |
|-------|-------------|
| **Compliance Logger (#1)** | `compliance_log` + workflow UI slice |
| **Proxy-Risk (#2)** | `proxy_risk` + workflow UI slice |
| **Alt-Data (#3)** | `altdata` + production feed registry |
| **AI Kit (#4)** | `ai_kit` + live LLM client |
| **Webhook Mesh (#5)** | `webhook_mesh` + Stripe/Shopify routes |
| **Ad Guard (#6)** | `ad_guard` + NeMo creative headers |
| **Health Telemetry (#7)** | `health_telemetry` + HIPAA/hospital packs |
| **Inst spine** | Genesis WAL, Lamport clocks, F1–F9 gates, deterministic export, verify-bundle |
| **Diligence pack** | 87 tests, rigorous E2E 7/7, buyer sheets, sales tech specs (all 7), demos |

**Pre-revenue reality:** Buyers pay for **risk reduction** (auditor-ready proof, fail-closed design, repeatable demo). Revenue multiples do not apply yet — use **cost-to-replicate** and **IP sale / acqui-hire comps**.

---

## Code inventory (honest floor)

| Component | Python LOC (approx) | Role |
|-----------|---------------------|------|
| `inst_spine` | ~2,600 | Shared — both products require it |
| `compliance_log` | ~240 | Product #1 only |
| `proxy_risk` | ~520 | Product #2 only |
| `inst_workflow` | ~350 + static UI | Optional console — both or single-product |
| Inst++ tests | ~1,500+ (subset) | Proof of correctness |

**Cost to replicate (internal estimate from deep dive):**  
2–3 **senior engineer-months** for genesis + WAL + F-gates + deterministic export — **before** product packaging, tests, docs, and buyer materials.

### Replacement cost (labour)

| Assumption | Low | Mid | High |
|------------|-----|-----|------|
| Senior engineer rate (UK contract) | £600/day | £750/day | £900/day |
| Calendar effort (genesis + spine + 2 products) | 40 days | 55 days | 70 days |
| **Labour replacement cost** | **£24k** | **£41k** | **£63k** |

Add **40–60%** for tests, docs, demos, institutional hardening → **£34k–£100k** all-in replacement.

---

## Valuation methods (pre-revenue)

### 1. Cost-to-replicate multiple

| Scenario | Multiple | Rationale |
|----------|----------|-----------|
| Raw code dump | 0.5–1.0× | No docs, no tests, buyer assumes rewrite risk |
| **Current package** (tests + docs + demos) | **1.5–2.5×** | Auditor-ready; demo in 60s |
| + design partner / pilot LOI | 2.5–4.0× | De-risked demand signal |
| + £50k+ ARR (first tenant) | 5–10× ARR | SaaS infra comps kick in |

**Current state (no revenue, full diligence):**

| Product | Share of spine | Standalone IP range |
|---------|----------------|---------------------|
| **Compliance Logger** | ~15% spine | **£25k–£75k** |
| **Proxy-Risk** | ~15% spine | **£30k–£90k** |
| **Alt-Data** | ~12% spine | **£20k–£50k** |
| **AI Kit** | ~10% spine | **£10k–£30k** |
| **Webhook Mesh** | ~12% spine | **£15k–£40k** |
| **Ad Guard** | ~12% spine | **£15k–£45k** |
| **Health Telemetry** | ~12% spine | **£30k–£80k** |
| **Combined (one spine, full pack)** | Single spine | **£60k–£130k** |

*USD equivalent at ~1.27: roughly **$32k–$165k** combined.*

### 2. Comparable pre-revenue B2B infra IP (market rough)

| Comp type | Typical pre-rev range | Fit |
|-----------|----------------------|-----|
| Niche open-source → commercial license | $0–$50k | Weak — not OSS community |
| **Acqui-hire / IP asset sale** (devtools, fintech infra) | $50k–$250k | **Strong** — air-gap, audit story |
| Seed-stage infra startup (pre-LOI) | $500k–$2M | Needs team + GTM, not code alone |
| Immutability / audit DB specialist acquisition | $1M+ | Needs traction + customers |

Inst++ today sits in the **IP asset / small acqui-hire** band — **not** seed-round company valuation without revenue and GTM.

### 3. Revenue potential (forward-looking, not current value)

| Product | Price band | 10 tenants Y1 | 25 tenants Y2 |
|---------|------------|---------------|---------------|
| Compliance Logger | £300–800/mo | £36k–96k ARR | £90k–240k ARR |
| Proxy-Risk | £400–1,200/mo | £48k–144k ARR | £120k–360k ARR |
| Alt-Data | £500–2,000/mo/feed | £60k–240k ARR | £150k–600k ARR |
| AI Kit | £50–249/seat | £6k–30k ARR | £15k–75k ARR |
| Webhook Mesh | £199–599/mo | £24k–72k ARR | £60k–180k ARR |
| Ad Guard | £300–800/mo | £36k–96k ARR | £90k–240k ARR |
| Health Telemetry | £5k–15k + £500/mo | £56k–156k ARR | £140k–390k ARR |

**Pre-revenue code value ≠ ARR.** First £50k ARR typically moves valuation from IP-sale framing to **3–8× ARR** for niche B2B infra.

---

## Value drivers (↑)

| Driver | Effect |
|--------|--------|
| Offline `verify-bundle` (auditor dry-run) | Rare — strong diligence wedge |
| 87 tests + logged rigorous E2E 7/7 | Reduces buyer rewrite risk |
| Sales tech specs + evidence pack (all 7) | Procurement-ready RFP depth |
| Air-gap / on-prem default | Fintech + regulated buyers |
| Separate SKUs + extraction docs | Clean procurement |
| Workflow UI per product (`--product`) | Demo without explaining the other SKU |
| Fail-closed design (documented) | Enterprise trust |

## Value draggers (↓)

| Drag | Effect |
|------|--------|
| No revenue / no LOI | IP-sale multiples only |
| Shared monorepo (`hibs-racing`) | Buyer sees sports adjacency — needs clean extract |
| No SOC 2 Type II | Enterprise security questionnaire friction |
| Python hot path | Quant buyers may discount vs Go/Rust |
| Single maintainer bus factor | Acquirer prices team risk |

---

## Recommended deal structures (pre-revenue)

| Structure | Typical range | Best for |
|-----------|---------------|----------|
| **IP license + source** (perpetual, one tenant) | £40k–£80k | Regulated buyer wants VPC deploy |
| **IP sale** (exclusive, one product) | £50k–£100k | Acquirer building compliance stack |
| **Acqui-hire** (code + 1–2 engineers) | £80k–£200k total | Fintech infra team gap-fill |
| **Royalty license** | £20k upfront + 8–15% rev share | Partner with distribution |
| **Combined bundle discount** | 15–25% off sum of singles | Same holding co buys both |

---

## Summary table

| Question | Answer |
|----------|--------|
| **Rough value of full portfolio (pre-rev)?** | **£60k–£130k** ($76k–$165k) |
| **#1 Compliance Logger alone?** | **£25k–£75k** |
| **#2 Proxy-Risk alone?** | **£30k–£90k** |
| **With first £50k ARR?** | Re-frame to **£250k–£350k** ecosystem (3–7× ARR) |
| **With pilot LOI from tier-1 fintech?** | Add **£25k–£50k** to IP floor |

---

## How to maximise pre-revenue price

1. **Clean extract repos** — `compliance-logger` and `proxy-risk` each with own `pyproject.toml`  
2. **One paid pilot** — even £500/mo LOI moves multiple  
3. **Auditor letter** — third party runs `verify-bundle` and signs one-pager  
4. **Remove sports adjacency** in buyer-facing repo name and README  
5. **SOC 2 roadmap** — Type I readiness doc (not certification required for IP sale)

---

## Related documents

- `docs/PORTFOLIO_SALES_SHEET.md` — commercial pricing matrix  
- `docs/BUYER_EVIDENCE_PACK.md` — procurement dry-run  
- `docs/COMPLIANCE_LOGGER_SALES_TECH_SPEC.md`  
- `docs/PROXY_RISK_SALES_TECH_SPEC.md`  
- `docs/ALTDATA_SALES_TECH_SPEC.md` through `HEALTH_TELEMETRY_SALES_TECH_SPEC.md`  
- `docs/INST_PLUS_DEEP_DIVE_ALL_7.md`  
- `docs/INST_PLUS_GOLD_STANDARD.md`
