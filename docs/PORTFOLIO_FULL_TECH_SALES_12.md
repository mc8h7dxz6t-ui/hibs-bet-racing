# Portfolio — Full Tech & Sales (12 SKUs)

**Audience:** Procurement, platform engineering, CFO sponsors, technical evaluators  
**Posture:** Air-gap VPC audit infrastructure — prove with math, not slides  
**Proof:** 157+ smoke tests · rigorous **12/12** · `industry_gold: true` · offline `verify-bundle` on every SKU  
**Date:** June 2026

> **License economics and valuation depth:** [PORTFOLIO_TECH_SALES_SHEET.md](PORTFOLIO_TECH_SALES_SHEET.md) · **One-page matrix:** [PORTFOLIO_SALES_SHEET.md](PORTFOLIO_SALES_SHEET.md) · **Evidence only (no prices):** [PORTFOLIO_EVIDENCE_SHEET.md](PORTFOLIO_EVIDENCE_SHEET.md) · **Platform compare:** [INST_PLUS_PLATFORM_COMPARE.md](INST_PLUS_PLATFORM_COMPARE.md)

---

## Portfolio pitch

*Twelve deployable products, one cryptographic audit spine — every gate decision exportable and verifiable without calling the vendor.*

---

## SKU index

| # | Product | SKU | Sale-now (perpetual VPC) | Full spec | Demo |
|---|---------|-----|--------------------------|-----------|------|
| 1 | Compliance Logger | `compliance-log` | £5,500 | [COMPLIANCE_LOGGER_SALES_TECH_SPEC.md](COMPLIANCE_LOGGER_SALES_TECH_SPEC.md) | `demo_compliance_logger.sh` |
| 2 | Proxy-Risk | `proxy-risk` | £10,500 | [PROXY_RISK_SALES_TECH_SPEC.md](PROXY_RISK_SALES_TECH_SPEC.md) | `demo_proxy_risk.sh` |
| 3 | Alt-Data | `altdata` | £7,000 | [ALTDATA_SALES_TECH_SPEC.md](ALTDATA_SALES_TECH_SPEC.md) | `demo_altdata.sh` |
| 4 | AI Kit | `ai-kit` | £1,400/seat | [AI_KIT_SALES_TECH_SPEC.md](AI_KIT_SALES_TECH_SPEC.md) | `demo_ai_kit.sh` |
| 5 | Webhook Mesh | `webhook-mesh` | £7,500 | [WEBHOOK_MESH_SALES_TECH_SPEC.md](WEBHOOK_MESH_SALES_TECH_SPEC.md) | `demo_webhook_mesh.sh` |
| 6 | Ad Guard | `ad-guard` | £5,500 | [AD_GUARD_SALES_TECH_SPEC.md](AD_GUARD_SALES_TECH_SPEC.md) | `demo_ad_guard.sh` |
| 7 | Health Telemetry | `health-telemetry` | £12,000–£14,000 | [HEALTH_TELEMETRY_SALES_TECH_SPEC.md](HEALTH_TELEMETRY_SALES_TECH_SPEC.md) | `demo_health_telemetry.sh` |
| 8 | ModelGovernor | `model-governor` | £8,000 | [MODEL_GOVERNOR_SALES_TECH_SPEC.md](MODEL_GOVERNOR_SALES_TECH_SPEC.md) | `demo_model_governor.sh` |
| 9 | Drift Gate | `drift-gate` | £16,000 | [DRIFT_GATE_SALES_TECH_SPEC.md](DRIFT_GATE_SALES_TECH_SPEC.md) | `demo_drift_gate.sh` |
| 10 | Webhook Replay | `webhook-replay` | £5,500 | [WEBHOOK_REPLAY_SALES_TECH_SPEC.md](WEBHOOK_REPLAY_SALES_TECH_SPEC.md) | `demo_webhook_replay.sh` |
| 11 | Spend Guard | `spend-guard` | £22,000 | [SPEND_GUARD_SALES_TECH_SPEC.md](SPEND_GUARD_SALES_TECH_SPEC.md) | `demo_spend_guard.sh` · `make demo-gold` |
| 12 | Agent Ledger | `agent-ledger` | £9,500 | [AGENT_LEDGER_SALES_TECH_SPEC.md](AGENT_LEDGER_SALES_TECH_SPEC.md) | `demo_agent_ledger.sh` |

**Buyer one-pagers:** `docs/*_BUYER.md`

---

## Vertical bundles (not separate SKUs)

| Bundle | SKUs | Sale-now band |
|--------|------|---------------|
| **Finance Governor** | #11 + #9 (+ #2 optional) | £38k–£48k |
| **Insurance Governor** | #8 + #9 + #1 | £26k–£32k |
| **Full spine** | All 12 | £110k–£180k |

---

## Shared spine

| Capability | All 12 |
|------------|--------|
| Genesis hash chain + Lamport clocks | ✅ |
| F1–F9 institutional check | ✅ |
| Deterministic export + `verify-bundle` | ✅ |
| Air-gap VPC SQLite + WAL | ✅ |
| Rigorous E2E section per SKU | ✅ |

**Production multi-instance:** [PRODUCTION_REDIS_PROFILE.md](PRODUCTION_REDIS_PROFILE.md) (#2, #5, #6, #9)

---

## Proof commands

```bash
make plug                    # install + demo-all + verify 12/12
make proof                   # smoke + rigorous + verify-portfolio
make demo-gold               # Spend Guard 11-step sales walkthrough
./scripts/instpp_rigorous_test.sh
cat docs/test_logs/instpp_rigorous_latest_summary.json
```

Expected summary: `"status": "PASSED"`, `"products": 12`, `"industry_gold": true`, `"e2e_sections": 39`

---

## GTM focus (pre-revenue)

**Cash tomorrow:** Proxy-Risk · Webhook Mesh · Spend Guard · Agent Ledger · Compliance Logger

See [ROADMAP_GTM_DISCIPLINE.md](ROADMAP_GTM_DISCIPLINE.md) for explicit non-SKUs.

---

## Related documents

| Doc | Purpose |
|-----|---------|
| [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) | Nine dimensions + completion matrix |
| [INSTITUTIONAL_STANDARD.md](INSTITUTIONAL_STANDARD.md) | Portfolio overview |
| [BUYER_EVIDENCE_PACK.md](BUYER_EVIDENCE_PACK.md) | 15-minute auditor dry-run |
| [RUN_DEMO.md](RUN_DEMO.md) | Plug / demo / run |
| [INST_PLUS_PRE_REV_VALUATION.md](INST_PLUS_PRE_REV_VALUATION.md) | IP valuation framework |
