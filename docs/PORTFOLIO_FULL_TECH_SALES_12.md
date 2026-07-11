# Portfolio — Full Tech & Sales (12 SKUs)

**Audience:** Procurement, platform engineering, CFO sponsors, technical evaluators  
**Posture:** Air-gap VPC audit infrastructure — prove with math, not slides  
**Proof:** 219+ smoke tests · rigorous **12/12** · `industry_gold: true` · offline `verify-bundle` on every SKU  
**Date:** July 2026

> **Start here:** [INST_PLUS_DILIGENCE_PACK.md](INST_PLUS_DILIGENCE_PACK.md) — self-contained tech/sales, evidence, and market compare (no Inst++ pricing in repo)

---

## Portfolio pitch

*Twelve deployable products, one cryptographic audit spine — every gate decision exportable and verifiable without calling the vendor.*

---

## SKU index

| # | Product | SKU | Full spec | Demo |
|---|---------|-----|-----------|------|
| 1 | Compliance Logger | `compliance-log` | [COMPLIANCE_LOGGER_SALES_TECH_SPEC.md](COMPLIANCE_LOGGER_SALES_TECH_SPEC.md) | `demo_compliance_logger.sh` |
| 2 | Proxy-Risk | `proxy-risk` | [PROXY_RISK_SALES_TECH_SPEC.md](PROXY_RISK_SALES_TECH_SPEC.md) | `demo_proxy_risk.sh` |
| 3 | Alt-Data | `altdata` | [ALTDATA_SALES_TECH_SPEC.md](ALTDATA_SALES_TECH_SPEC.md) | `demo_altdata.sh` |
| 4 | AI Kit | `ai-kit` | [AI_KIT_SALES_TECH_SPEC.md](AI_KIT_SALES_TECH_SPEC.md) | `demo_ai_kit.sh` |
| 5 | Webhook Mesh | `webhook-mesh` | [WEBHOOK_MESH_SALES_TECH_SPEC.md](WEBHOOK_MESH_SALES_TECH_SPEC.md) | `demo_webhook_mesh.sh` |
| 6 | Ad Guard | `ad-guard` | [AD_GUARD_SALES_TECH_SPEC.md](AD_GUARD_SALES_TECH_SPEC.md) | `demo_ad_guard.sh` |
| 7 | Health Telemetry | `health-telemetry` | [HEALTH_TELEMETRY_SALES_TECH_SPEC.md](HEALTH_TELEMETRY_SALES_TECH_SPEC.md) | `demo_health_telemetry.sh` |
| 8 | ModelGovernor | `model-governor` | [MODEL_GOVERNOR_SALES_TECH_SPEC.md](MODEL_GOVERNOR_SALES_TECH_SPEC.md) | `demo_model_governor.sh` |
| 9 | Drift Gate | `drift-gate` | [DRIFT_GATE_SALES_TECH_SPEC.md](DRIFT_GATE_SALES_TECH_SPEC.md) | `demo_drift_gate.sh` |
| 10 | Webhook Replay | `webhook-replay` | [WEBHOOK_REPLAY_SALES_TECH_SPEC.md](WEBHOOK_REPLAY_SALES_TECH_SPEC.md) | `demo_webhook_replay.sh` |
| 11 | Spend Guard | `spend-guard` | [SPEND_GUARD_SALES_TECH_SPEC.md](SPEND_GUARD_SALES_TECH_SPEC.md) | `demo_spend_guard.sh` · `make demo-gold` |
| 12 | Agent Ledger | `agent-ledger` | [AGENT_LEDGER_SALES_TECH_SPEC.md](AGENT_LEDGER_SALES_TECH_SPEC.md) | `demo_agent_ledger.sh` |

**Full tech/sales depth:** [PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md](PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md) · **Buyer one-pagers:** `docs/*_BUYER.md`

---

## Vertical bundles (not separate SKUs)

| Bundle | SKUs | Job |
|--------|------|-----|
| **Finance Governor** | #11 + #9 (+ #2 optional) | LLM/API spend + drift enforce + outbound firewall |
| **Insurance Governor** | #8 + #9 + #1 | Model lifecycle + drift + decision audit |
| **Full spine** | All 12 | One `PORTFOLIO_MANIFEST.json` over 12 verify-bundle |

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
| [INST_PLUS_DILIGENCE_PACK.md](INST_PLUS_DILIGENCE_PACK.md) | **Start here** — self-contained diligence pack |
| [PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md](PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md) | Full tech + sales per SKU |
| [PORTFOLIO_EVIDENCE_SHEET.md](PORTFOLIO_EVIDENCE_SHEET.md) | CI proof and test artifacts |
| [INST_PLUS_PLATFORM_COMPARE.md](INST_PLUS_PLATFORM_COMPARE.md) | Market compare + comparable pricing |
| [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) | Nine dimensions + completion matrix |
| [BUYER_EVIDENCE_PACK.md](BUYER_EVIDENCE_PACK.md) | 15-minute auditor dry-run |
| [RUN_DEMO.md](RUN_DEMO.md) | Plug / demo / run |
