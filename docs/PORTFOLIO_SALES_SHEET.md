# Portfolio Sales Sheet — 8 Institutional Products

**Audience:** Procurement, legal, risk, platform engineering, CFO sponsors  
**Posture:** Air-gap VPC audit infrastructure — **prove with math, not slides**  
**Proof:** 91 automated tests · rigorous E2E 8/8 · offline `verify-bundle` on every SKU

---

## One-line portfolio pitch

*Eight deployable products, one cryptographic audit spine — every gate decision exportable and verifiable without calling the vendor.*

---

## Product matrix (sell separately or as spine bundle)

| # | Product | One job | Price band | Ideal buyer | Demo | Full spec |
|---|---------|---------|------------|-------------|------|-----------|
| 1 | **Compliance Logger** | Tamper-proof regulated decision audit | £300–£800/mo | Fintech ops, legal, UK sport NGBs | `demo_compliance_logger.sh` | [COMPLIANCE_LOGGER_SALES_TECH_SPEC.md](COMPLIANCE_LOGGER_SALES_TECH_SPEC.md) |
| 2 | **Proxy-Risk** | Outbound API firewall + cryptographic audit | £400–£1,200/mo | Broker ops, quant infra, payments | `demo_proxy_risk.sh` | [PROXY_RISK_SALES_TECH_SPEC.md](PROXY_RISK_SALES_TECH_SPEC.md) |
| 3 | **Alt-Data** | Clean feed with coverage SLA + poll proof | £500–£2,000/mo per feed | Quant, data eng, compliance feeds | `demo_altdata.sh` | [ALTDATA_SALES_TECH_SPEC.md](ALTDATA_SALES_TECH_SPEC.md) |
| 4 | **AI Kit** | Agent rate limits, checkpoints, trace audit | £99–£249/seat | Platform teams shipping agents | `demo_ai_kit.sh` | [AI_KIT_SALES_TECH_SPEC.md](AI_KIT_SALES_TECH_SPEC.md) |
| 5 | **Webhook Mesh** | Never double-process a billing webhook | £199–£599/mo | SaaS billing, fintech ingress | `demo_webhook_mesh.sh` | [WEBHOOK_MESH_SALES_TECH_SPEC.md](WEBHOOK_MESH_SALES_TECH_SPEC.md) |
| 6 | **Ad Guard** | Marketing API spend kill + gate audit | £300–£800/mo | Agency, growth, marketing finance | `demo_ad_guard.sh` | [AD_GUARD_SALES_TECH_SPEC.md](AD_GUARD_SALES_TECH_SPEC.md) |
| 7 | **Health Telemetry** | Device batch tamper evidence (not FDA cert) | £5k–£15k + £500/mo | Digital health, RPM, NHS-adjacent | `demo_health_telemetry.sh` | [HEALTH_TELEMETRY_SALES_TECH_SPEC.md](HEALTH_TELEMETRY_SALES_TECH_SPEC.md) |
| 8 | **ModelGovernor** | ML model lifecycle governance + deploy proof ([north star](MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md): LLM spend plane) | £400–£1,000/mo | MLOps, model risk, regulated lending | `demo_model_governor.sh` | [MODEL_GOVERNOR_SALES_TECH_SPEC.md](MODEL_GOVERNOR_SALES_TECH_SPEC.md) |

**Buyer one-pagers:** `docs/*_BUYER.md` (60-second skim per SKU)

---

## Why buyers pick us (shared spine)

| Pain | Industry default | Portfolio answer |
|------|------------------|------------------|
| “Prove what happened on date X” | Editable CSV / dashboard trust | Genesis hash chain + deterministic export |
| Auditor needs offline replay | Vendor callback / live DB | `verify-bundle` on tarball only |
| Clock spoofing / device drift | Wall-clock timestamps | Lamport logical clocks (F4) |
| Silent data gaps | Alert after the fact | Fail-closed gates (F7 coverage, rate limits) |
| Vendor lock-in | SaaS-only | Air-gap VPC — buyer holds ledger |
| Multi-instance dedupe | In-memory only | Redis fail-closed CAS |

**Spine IP floor:** 2–3 senior engineer-months to replicate `inst_spine` alone (~£34k–£100k replacement cost).

---

## Commercial packaging

| Package | Contents | Band |
|---------|----------|------|
| **Single SKU license** | CLI + spine + export + verify-bundle + demo script | Per table above |
| **Spine bundle (2+ SKUs)** | Shared `inst_spine`, one anchor ceremony, unified export tooling | 15% discount on 2nd+ SKU |
| **Workflow console** | Browser 5-step proof UI (#1 + #2 today) | Included with #1/#2 |
| **Design partner** | Live URL / upstream wiring + schema mapping SOW | £2k–£8k one-time |
| **Hospital / enterprise pilot** | HIPAA pack + ward playbook (#7) or SOC VPC pack (all) | Custom SOW |
| **Maintenance** | Security patches, spine upgrades | 15–20% ARR |

**Full tech/sales sheet (per-platform comps + revenue + value):** [PORTFOLIO_TECH_SALES_SHEET.md](PORTFOLIO_TECH_SALES_SHEET.md)

---

## 15-minute diligence (procurement dry-run)

```bash
pip install -e ".[dev,instpp]"
./scripts/instpp_smoke_test.sh          # 91 tests
./scripts/instpp_rigorous_test.sh       # 8/8 E2E → docs/test_logs/
./scripts/demo_instpp.sh                # all demos
```

**Evidence artifacts:** [BUYER_EVIDENCE_PACK.md](BUYER_EVIDENCE_PACK.md) · [SOC2_VPC_DILIGENCE_PACK.md](SOC2_VPC_DILIGENCE_PACK.md)

| Artifact | Path |
|----------|------|
| Latest rigorous summary | `docs/test_logs/instpp_rigorous_latest_summary.json` |
| Latest rigorous log | `docs/test_logs/instpp_rigorous_latest.log` |
| Institutional standard | `docs/INSTITUTIONAL_STANDARD.md` |

---

## RFP quick answers (portfolio)

| Question | Answer |
|----------|--------|
| Tamper-evident audit trail? | **Yes** — all 8 SKUs |
| Offline third-party verification? | **Yes** — `verify-bundle` |
| Air-gapped VPC deploy? | **Yes** — default architecture |
| SOC 2 Type II certified SaaS? | **No** — buyer VPC; see SOC2 pack |
| GRC case management UI? | **No** — export into Archer/ServiceNow |
| Sub-5ms RTB / exchange insert? | **No** — Go/Rust territory |
| LLM safety inference? | **No** — NeMo/Bedrock upstream of Ad Guard |
| Model governance / deploy proof? | **Yes** — #8 ModelGovernor |
| FDA / DTAC medical device cert? | **No** — audit spine only (#7) |

---

## Pilot ladder (recommended close)

| Stage | Duration | Deliverable | Buyer commitment |
|-------|----------|-------------|------------------|
| **1. Dry-run** | 1 meeting | Run demo script + `verify-bundle` on sample tarball | Technical evaluator |
| **2. Shadow** | 2–4 weeks | Deploy in VPC; shadow mode (#2, #6) or read-only poll (#3) | Eng + security sign-off |
| **3. Live pilot** | 4–8 weeks | Single tenant, one feed/route/ward | LOI or paid pilot £2k–£8k |
| **4. Production** | — | Annual license + 15–20% maintenance | MSA + order form |

---

## Stack map (where products sit)

```
Upstream safety          Portfolio gates              Proof
─────────────────        ─────────────────            ─────
NeMo / Bedrock    →      Ad Guard (spend)      →      verify-bundle
Stripe / Shopify  →      Webhook Mesh          →      verify-bundle
Business apps     →      Compliance Logger     →      verify-bundle
Outbound APIs     →      Proxy-Risk            →      verify-bundle
Alt-data sources  →      Alt-Data              →      verify-bundle
Agent workloads   →      AI Kit                →      verify-bundle
Device batches    →      Health Telemetry      →      verify-bundle
ML model lifecycle →     ModelGovernor         →      verify-bundle
```

---

## Related documents

| Doc | Purpose |
|-----|---------|
| [INST_PLUS_DEEP_DIVE_ALL_7.md](INST_PLUS_DEEP_DIVE_ALL_7.md) | Technical deep dive per product |
| [INST_PLUS_PRE_REV_VALUATION.md](INST_PLUS_PRE_REV_VALUATION.md) | IP valuation framework |
| [INSTITUTIONAL_ENTERPRISE_STACK.md](INSTITUTIONAL_ENTERPRISE_STACK.md) | Enterprise positioning |
| [TECHNICAL_DUE_DILIGENCE_FAQ.md](TECHNICAL_DUE_DILIGENCE_FAQ.md) | FAQ for technical buyers |
| [DEMO.md](DEMO.md) | Demo command reference |
