# Portfolio Roadmap — Master Sales Sheet

**Audience:** Buyers evaluating a code-only, pre-revenue asset sale  
**Repo:** `hibs-bet-racing` Institutional++ portfolio (12 SKUs + 4 governor bundles)  
**Proof posture:** Offline `verify-bundle` on every SKU · rigorous 12/12 · governor-tier CI  
**Date:** July 2026

> **Honesty guardrail:** Governors **IG / FG / MG / CG** are **sales bundle labels** over real SKUs — not separate runnable microservices. See [compliance/README.md](../compliance/README.md) and [FORENSIC_ARCHITECTURE_TRUTH.md](../FORENSIC_ARCHITECTURE_TRUTH.md).

---

## Executive summary

| Layer | Count | Status |
|-------|-------|--------|
| **Standalone programs (SKUs)** | 12 | Shipped — CLI + `verify-bundle` each |
| **Governor bundles** | 4 | Sales packaging over SKU combinations |
| **Shared spine** | `inst_spine` | Genesis chain, Lamport, F1–F9, export/verify |
| **Industry gold** | Rigorous E2E | 12/12 PASSED (`industry_gold: true`) |

**Cyber Governor (CG)** maps to Webhook Mesh (#5) + Ad Guard (#6) — **100% institutional bar** on shipped code (chaos + WAL ingress proofs in CI).

---

## Twelve standalone programs

| # | SKU | Job-to-be-done | Maturity | Full spec |
|---|-----|----------------|----------|-----------|
| 1 | Compliance Logger | Append-only decision audit | Inst++ ✅ | [COMPLIANCE_LOGGER_SALES_TECH_SPEC.md](../COMPLIANCE_LOGGER_SALES_TECH_SPEC.md) |
| 2 | Proxy-Risk | Outbound API firewall + rate/shadow | Inst++ ✅ | [PROXY_RISK_SALES_TECH_SPEC.md](../PROXY_RISK_SALES_TECH_SPEC.md) |
| 3 | Alt-Data | Coverage + provenance polling | Inst++ ✅ | [ALTDATA_SALES_TECH_SPEC.md](../ALTDATA_SALES_TECH_SPEC.md) |
| 4 | AI Kit | Tool-auth agent loop | Inst++ ✅ | [AI_KIT_SALES_TECH_SPEC.md](../AI_KIT_SALES_TECH_SPEC.md) |
| 5 | **Webhook Mesh** | Lamport webhook fan-out + DLQ | Inst++ ✅ | [WEBHOOK_MESH_SALES_TECH_SPEC.md](../WEBHOOK_MESH_SALES_TECH_SPEC.md) |
| 6 | Ad Guard | Creative compliance + spend hook | Inst++ ✅ | [AD_GUARD_SALES_TECH_SPEC.md](../AD_GUARD_SALES_TECH_SPEC.md) |
| 7 | Health Telemetry | Seq-gated WAL ingress | Inst++ ✅ | [HEALTH_TELEMETRY_SALES_TECH_SPEC.md](../HEALTH_TELEMETRY_SALES_TECH_SPEC.md) |
| 8 | ModelGovernor | Model lifecycle FSM + artifact hash | Inst++ ✅ | [MODEL_GOVERNOR_SALES_TECH_SPEC.md](../MODEL_GOVERNOR_SALES_TECH_SPEC.md) |
| 9 | Drift Gate | PSI/KS enforce at hot path | Inst++ ✅ | [DRIFT_GATE_SALES_TECH_SPEC.md](../DRIFT_GATE_SALES_TECH_SPEC.md) |
| 10 | Webhook Replay | WRCAP mmap air-gap replay | Inst++ ✅ | [WEBHOOK_REPLAY_SALES_TECH_SPEC.md](../WEBHOOK_REPLAY_SALES_TECH_SPEC.md) |
| 11 | Spend Guard | Reserve/settle LLM wallet + gateway | Inst++ ✅ | [SPEND_GUARD_SALES_TECH_SPEC.md](../SPEND_GUARD_SALES_TECH_SPEC.md) |
| 12 | Agent Ledger | Runtime tool authorization | Inst++ ✅ | [AGENT_LEDGER_SALES_TECH_SPEC.md](../AGENT_LEDGER_SALES_TECH_SPEC.md) |

**Deep dive (no prices):** [PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md](../PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md)

---

## Four governor bundles

| Bundle | SKUs | Buyer job | Tier 1 CI | Tier 2 CI |
|--------|------|-----------|-----------|-----------|
| **Finance Governor (FG)** | #11 + #9 (+ #2 optional) | LLM/API spend + drift enforce + egress | spend/drift/proxy forensic | Postgres wallet + ledger |
| **Insurance Governor (IG)** | #8 + #9 + #1 | Model lifecycle + drift + decision audit | MG + drift + compliance | Postgres compliance chain |
| **Model Governor (MG)** | #8 | Artifact hash + deploy FSM | model-governor + buyer depth | Postgres spine attestation |
| **Cyber Governor (CG)** | #5 + #6 | Webhook security + creative guard | mesh chaos + ad-guard | Postgres chain attestation |

CI workflow: `.github/workflows/ci.yml` — matrix `Governor — Tier` (institutional + Postgres).

---

## Brief vs-competitor positioning

| Wedge | Closest SaaS | Our differentiation |
|-------|--------------|---------------------|
| Spend + drift plane | LiteLLM / Portkey / FinOps dashboards | Reserve-before-dispatch + drift lockout on same wallet; air-gap `verify-bundle` |
| Webhook mesh | Hookdeck / Svix | Lamport ordering + DLQ on cryptographic ledger; chaos CI |
| Model lifecycle | MLflow / internal MLOps | Deploy drift gate + artifact hash mismatch reject; no multi-tenant SaaS tax |
| Compliance audit | Immuta / Collibra (partial) | F1–F9 gates + offline examiner pack per SKU |
| Agent tool auth | Custom IAM | Policy gate tied to spend wallet + compliance chain |

Full compare: [INST_PLUS_PLATFORM_COMPARE.md](../INST_PLUS_PLATFORM_COMPARE.md)

---

## Code-only pre-revenue asset sale framing

**What a buyer gets today (no revenue, no tenants):**

| Asset | Evidence |
|-------|----------|
| 12 deployable Python CLIs + FastAPI serves | `make plug` → verify 12/12 |
| Shared `inst_spine` library | 246+ smoke tests |
| Docker / K8s profiles | `docker-compose.instpp.yml`, `deploy/k8s/` |
| Buyer diligence pack | [INST_PLUS_DILIGENCE_PACK.md](../INST_PLUS_DILIGENCE_PACK.md) |
| SOC2-oriented evidence generator | `make soc2-evidence` |

**Pricing:** Not in repo — negotiate offline per SKU or full portfolio. Reference bands in buyer conversations only (see ModelGovernor positioning doc: £25k–£70k per wedge SKU; portfolio multiples higher).

**Not included without SOW:** ClaimGate, four-governor microservices, NAIC/SOC2 attestation letters, hosted SaaS.

---

## Roadmap phases (engineering)

| Phase | Focus | Status |
|-------|-------|--------|
| **L2** | Competitive gaps bridged — golden PSI/KS, idempotency matrix, API key on spend gateway | ✅ Shipped |
| **L4 Gold** | Postgres profile, Toxiproxy chaos hooks, MG+FG cross-wire tests, K8s init containers | ✅ Postgres CI; K8s profile in compose |
| **Forensic audit** | Invariant fixes, rigorous test pyramid, Proof Console 12/12 | ✅ `instpp_rigorous_test.sh` |
| **GTM** | Proxy-Risk · Webhook Mesh · Spend Guard · Agent Ledger · Compliance Logger | Pre-revenue — [ROADMAP_GTM_DISCIPLINE.md](../ROADMAP_GTM_DISCIPLINE.md) |

---

## Verify commands

```bash
make plug                          # 12/12 offline verify
make proof                         # smoke + rigorous + portfolio
./scripts/instpp_governor_tier.sh  # INST_GOVERNOR=finance INST_TIER=1
INST_TEST_POSTGRES_DSN=postgresql://... INST_GOVERNOR=finance INST_TIER=2 ./scripts/instpp_governor_tier.sh
```

---

## Related documents

| Doc | Purpose |
|-----|---------|
| [PORTFOLIO_FULL_TECH_SALES_12.md](../PORTFOLIO_FULL_TECH_SALES_12.md) | SKU index + proof commands |
| [PORTFOLIO_DEEP_DIVE.md](../PORTFOLIO_DEEP_DIVE.md) | Racing portfolio Inst++ roadmaps |
| [INST_PLUS_GOLD_STANDARD.md](../INST_PLUS_GOLD_STANDARD.md) | Nine-dimension completion matrix |
| [BUYER_EVIDENCE_PACK.md](../BUYER_EVIDENCE_PACK.md) | 15-minute auditor dry-run |
