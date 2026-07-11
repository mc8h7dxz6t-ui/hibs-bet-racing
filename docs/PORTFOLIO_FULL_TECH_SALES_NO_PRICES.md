# Institutional++ — Full Tech & Sales Sheet

**Audience:** Procurement, platform engineering, model risk, auditors, CFO sponsors  
**Posture:** Air-gap VPC audit infrastructure — prove with math, not slides  
**Proof:** 219+ smoke tests · rigorous **12/12** · `industry_gold: true` · offline `verify-bundle` on every SKU  
**Scope:** SKU / Inst++ only (not sports, trading overlay, or governor consumer apps)  
**Date:** July 2026

> **Part of the self-contained diligence pack** — [INST_PLUS_DILIGENCE_PACK.md](INST_PLUS_DILIGENCE_PACK.md)  
> **Evidence & CI proof:** [PORTFOLIO_EVIDENCE_SHEET.md](PORTFOLIO_EVIDENCE_SHEET.md)  
> **Capability compare:** [INST_PLUS_PLATFORM_COMPARE.md](INST_PLUS_PLATFORM_COMPARE.md)  
> **No pricing in diligence pack docs.**

---

## Portfolio pitch

*Twelve deployable products, one cryptographic audit spine — every gate decision exportable and verifiable without calling the vendor.*

| # | Product | SKU | Demo | Deep spec |
|---|---------|-----|------|-----------|
| 1 | Compliance Logger | `compliance-log` | `demo_compliance_logger.sh` | [COMPLIANCE_LOGGER_SALES_TECH_SPEC.md](COMPLIANCE_LOGGER_SALES_TECH_SPEC.md) |
| 2 | Proxy-Risk | `proxy-risk` | `demo_proxy_risk.sh` | [PROXY_RISK_SALES_TECH_SPEC.md](PROXY_RISK_SALES_TECH_SPEC.md) |
| 3 | Alt-Data | `altdata` | `demo_altdata.sh` | [ALTDATA_SALES_TECH_SPEC.md](ALTDATA_SALES_TECH_SPEC.md) |
| 4 | AI Kit | `ai-kit` | `demo_ai_kit.sh` | [AI_KIT_SALES_TECH_SPEC.md](AI_KIT_SALES_TECH_SPEC.md) |
| 5 | Webhook Mesh | `webhook-mesh` | `demo_webhook_mesh.sh` | [WEBHOOK_MESH_SALES_TECH_SPEC.md](WEBHOOK_MESH_SALES_TECH_SPEC.md) |
| 6 | Ad Guard | `ad-guard` | `demo_ad_guard.sh` | [AD_GUARD_SALES_TECH_SPEC.md](AD_GUARD_SALES_TECH_SPEC.md) |
| 7 | Health Telemetry | `health-telemetry` | `demo_health_telemetry.sh` | [HEALTH_TELEMETRY_SALES_TECH_SPEC.md](HEALTH_TELEMETRY_SALES_TECH_SPEC.md) |
| 8 | ModelGovernor | `model-governor` | `demo_model_governor.sh` · `make demo-mg-gold` | [MODEL_GOVERNOR_SALES_TECH_SPEC.md](MODEL_GOVERNOR_SALES_TECH_SPEC.md) |
| 9 | Drift Gate | `drift-gate` | `demo_drift_gate.sh` | [DRIFT_GATE_SALES_TECH_SPEC.md](DRIFT_GATE_SALES_TECH_SPEC.md) |
| 10 | Webhook Replay | `webhook-replay` | `demo_webhook_replay.sh` | [WEBHOOK_REPLAY_SALES_TECH_SPEC.md](WEBHOOK_REPLAY_SALES_TECH_SPEC.md) |
| 11 | Spend Guard | `spend-guard` | `demo_spend_guard.sh` · `make demo-gold` | [SPEND_GUARD_SALES_TECH_SPEC.md](SPEND_GUARD_SALES_TECH_SPEC.md) |
| 12 | Agent Ledger | `agent-ledger` | `demo_agent_ledger.sh` | [AGENT_LEDGER_SALES_TECH_SPEC.md](AGENT_LEDGER_SALES_TECH_SPEC.md) |

**Buyer one-pagers:** `docs/*_BUYER.md`

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

| Capability | All 12 |
|------------|--------|
| Genesis hash chain + Lamport clocks | ✅ |
| F1–F9 institutional check | ✅ |
| Deterministic export + `verify-bundle` | ✅ |
| Air-gap VPC SQLite + WAL | ✅ |
| Rigorous E2E section per SKU | ✅ |
| Bundle HMAC signing (rigorous wave 4) | ✅ |

**Production multi-instance:** [PRODUCTION_REDIS_PROFILE.md](PRODUCTION_REDIS_PROFILE.md) (#2, #5, #6, #9)  
**Architecture + execution map:** [INST_PLUS_PRODUCTION_ARCHITECTURE.md](INST_PLUS_PRODUCTION_ARCHITECTURE.md)

---

## Portfolio proof envelope

| Layer | Command | What it proves |
|-------|---------|----------------|
| Plug | `make plug` | Install + demo-all 12/12 + offline verify |
| Smoke | `./scripts/instpp_smoke_test.sh` | 219+ institutional pytest tests |
| Proof-lite | `./scripts/instpp_proof_lite.sh` | Production profile gates + portfolio verify |
| Rigorous | `./scripts/instpp_rigorous_test.sh` | 45 E2E sections, forensic waves 1–4 |
| Full proof | `make proof` | Smoke + rigorous + verify-portfolio |
| Docker extended | `make docker-extended` | Redis + Postgres compose, zero-skip rigorous |
| Buyer pack | `make buyer-pack` | `PORTFOLIO_MANIFEST.json` + bundle tarballs |
| SOC2 evidence | `make soc2-evidence` | VPC evidence JSON from verified manifest |

**Logged artifacts:** `docs/test_logs/` — see [test_logs/README.md](test_logs/README.md)

---

## Completion at a glance

| # | Product | Grade | Inst | Prod | Comm | GTM headline |
|---|---------|-------|------|------|------|--------------|
| 1 | Compliance Logger | **Gold** | ✅ | ✅ | ✅ | No GRC workflow / SOC2 SaaS |
| 2 | Proxy-Risk | **Gold** | ✅ | ✅ | ✅ | Scale: Redis for multi-instance live |
| 3 | Alt-Data | **Gold** | ✅ | ✅ | ✅ | Buyer feeds: integration SOW |
| 4 | AI Kit | **Gold** | ✅ | ✅ | ✅ | Hardest standalone sell |
| 5 | Webhook Mesh | **Gold** | ✅ | ✅ | ✅ | Scale: Redis Stream queue |
| 6 | Ad Guard | **Gold** | ✅ | ✅ | ✅ | Not RTB / DSP UI |
| 7 | Health Telemetry | **Gold** | ✅ | ✅ | ✅ | Audit spine, not FDA cert |
| 8a | ModelGovernor lifecycle | **Gold** | ✅ | ✅ | ✅ | Not full MLOps platform |
| 8b | Spend plane (`demo-gold`) | **Demo gold** | 🟡 | 🟡 | ✅ | Canonical walkthrough, not separate CI SKU |
| 9 | Drift Gate | **Gold** | ✅ | ✅ | ✅ | Scale: Redis rolling windows |
| 10 | Webhook Replay | **Gold** | ✅ | ✅ | ✅ | Air-gapped byte replay |
| 11 | Spend Guard CLI | **Gold** | ✅ | ✅ | ✅ | Scale: Postgres wallet optional |
| 12 | Agent Ledger | **Gold** | ✅ | ✅ | ✅ | Pre-exec tool governance |

**Layers:** Inst = F1–F9 + verify-bundle + rigorous E2E · **Prod** = single-instance VPC deploy envelope ([architecture](INST_PLUS_PRODUCTION_ARCHITECTURE.md)) · Comm = buyer + sales spec + demo · GTM = paying tenants (pre-revenue today)

---

# Per platform (sales + tech, no pricing)

---

## 1 — Compliance Logger

**One job:** Tamper-proof regulated **business decision** audit — snapshot + outcome + hash chain, offline `verify-bundle`.

**Pitch:** *Prove the approval on date X — with math, not a spreadsheet.*

### Ideal buyer

| Segment | Pain | Answer |
|---------|------|--------|
| Fintech / payments ops | Prove system decision on date X | Genesis chain + export bundle |
| Legal / risk / compliance | CSV exports are editable | Deterministic tar + SHA256 sidecar |
| Governance / NGB adjacency | Audit without consumer app | Infrastructure-only SKU |

### Problem → solution

| Buyer pain | Industry default | Compliance Logger |
|------------|------------------|-------------------|
| “Prove decision on date X” | CSV/PDF (editable) | Snapshot + outcome + hash chain |
| Auditor distrust | “Trust our dashboard” | Offline `verify-bundle` |
| Clock spoofing | Wall-clock timestamps | Lamport clocks (F4) |
| Reproducibility disputes | Non-deterministic exports | F9 — identical ledger → identical SHA256 |

### Competitive comparison (capability)

| Capability | GRC SaaS | immudb / QLDB | **Compliance Logger** |
|------------|----------|---------------|----------------------|
| Decision snapshot contract | Custom fields | BYO schema | **First-class ingest** |
| Offline auditor replay | No | Partial | **Tarball only** |
| Deterministic export hash | No | No | **F9 gate** |
| Workflow UI | Strong | None | **Proof console** |
| Air-gap default | Rare | Yes | **Yes** |
| mTLS ingest | Typical | Typical | **Proven (rigorous)** |
| Epoch roots in export | Gap | Partial | **Proven (phase 3)** |

**Win when:** buyer needs **proof**, not case management.  
**Lose when:** buyer needs ServiceNow workflow or certified multi-tenant SaaS day one.

### Tech proof

```bash
./scripts/demo_compliance_logger.sh
compliance-log verify-bundle --tarball ./data/demo/portfolio/compliance_bundle.tar
```

| Layer | Status | Detail |
|-------|--------|--------|
| Institutional gold | ✅ | F1–F9; rigorous E2E; mTLS; epoch roots |
| Production | ✅ | Air-gap SQLite + WAL; optional Postgres |
| CI | ✅ | `compliance_logger` in rigorous summary — PASSED |

---

## 2 — Proxy-Risk

**One job:** Outbound API **firewall** — rate limit, Z-score kill, idempotency, shadow → live, every gate on chain.

**Pitch:** *Stop runaway outbound API spend and prove every approve/reject/kill.*

### Gate chain (hot path)

```
circuit → schema → token bucket → idempotency → z-score drift → [shadow | live forward]
```

| Mode | Behavior |
|------|----------|
| **Shadow** | Gates run; no upstream call; ledger append async |
| **Live** | Sync WAL before upstream; 4xx/5xx → REJECT (fail-closed) |

**Latency target:** p99 &lt; 10ms shadow (industry gold tests)

### Competitive comparison (capability)

| Capability | API gateway (Kong) | WAF / rate SaaS | **Proxy-Risk** |
|------------|-------------------|-----------------|----------------|
| Shadow burn-in | No | No | **Default** |
| Kill switch + Z-score | Rare | Sometimes | **Yes** |
| Audit per gate outcome | Access log | Metrics | **Genesis chain** |
| Offline verify | No | No | **verify-bundle** |
| Drift integration | Gap | Gap | **#9 Drift Gate baseline** |

**Win when:** fail-closed outbound control + proof.  
**Lose when:** sub-5ms RTB or full API lifecycle platform.

### Tech proof

```bash
./scripts/demo_proxy_risk.sh
proxy-risk verify-bundle --tarball ./data/demo/portfolio/proxy_bundle.tar
```

| Layer | Status | Detail |
|-------|--------|--------|
| Institutional gold | ✅ | Full gate chain; p99 bench |
| Production | ✅ | Single-instance VPC; scale: Redis for live multi-replica |
| CI | ✅ | `proxy_risk` rigorous — PASSED |

---

## 3 — Alt-Data

**One job:** Clean alt-data feed with **coverage SLA** — 4-rung fetch ladder, F7 fail-closed, tamper-evident poll log.

**Pitch:** *Prove the feed wasn't silently empty on date X.*

### Competitive comparison (capability)

| Capability | Generic scrapers | ETL SaaS (Fivetran) | **Alt-Data** |
|------------|------------------|---------------------|--------------|
| Coverage as gate | Ad-hoc | Dashboard | **F7 institutional** |
| Structural rescue | Rare | Manual | **Rung-4 golden path** |
| Tamper-evident poll log | No | No | **Genesis per poll** |
| Offline verify | No | No | **verify-bundle** |

**Win when:** coverage SLA + poll proof.  
**Lose when:** full ETL catalog or exchange tick latency.

### Tech proof

```bash
./scripts/demo_altdata.sh
altdata verify-bundle --tarball ./data/demo/portfolio/altdata_bundle.tar
```

---

## 4 — AI Kit

**One job:** Production **agent guardrails** — rate limits, Lamport checkpoints, trace ledger, optional live LLM.

**Pitch:** *Run agents in production with checkpoints and an audit trail auditors can verify offline.*

### Competitive comparison (capability)

| Capability | LangChain defaults | LangSmith / Langfuse | **AI Kit** |
|------------|-------------------|----------------------|------------|
| Crash-safe resume | Varies | N/A | **Lamport checkpoints** |
| Agent trace audit | Logs | SaaS dashboard | **Ledger + verify-bundle** |
| Air-gap deploy | Rare | No | **Yes** |
| step_fn contract | Gap | Gap | **Phase 3 rigorous** |

**Win when:** production guardrails + offline trace audit.  
**Lose when:** LangGraph ecosystem, hosted observability UI.

---

## 5 — Webhook Mesh

**One job:** **Never double-process** a billing webhook — HMAC verify, Redis idempotency, WAL before 200, genesis ingress ledger.

**Pitch:** *Ack webhooks only after durability — with cryptographic proof you never charged twice.*

### Ingress path

```
HMAC verify → Redis SETNX idempotency → WAL fsync → HTTP 200 → Redis stream forward
```

### Competitive comparison (capability)

| Capability | Stripe idempotency | Svix / Hookdeck | **Webhook Mesh** |
|------------|-------------------|-----------------|------------------|
| WAL before provider ack | No | Typical | **Yes** |
| Multi-instance dedupe | Stripe-only | Typical | **Redis Lua CAS** |
| Offline verify on ledger | No | Gap | **verify-bundle** |
| Byte-identical replay | No | Partial | **#10 Webhook Replay** |

**Win when:** idempotent ingress + audit proof in VPC.  
**Lose when:** managed multi-tenant webhook SaaS at infinite scale.

---

## 6 — Ad Guard

**One job:** Marketing API **spend kill** at the boundary — Google/Meta parsers, Z-score kill, genesis gate audit.

**Pitch:** *Stop runaway Google/Meta API spend before finance sees the bill.*

### Competitive comparison (capability)

| Capability | Finance alerts | DSP native caps | **Ad Guard** |
|------------|----------------|-----------------|--------------|
| API-boundary kill | Post-hoc | Partial | **Pre-forward Z-score** |
| Google/Meta parsers | Manual | N/A | **Built-in** |
| Every gate logged | No | No | **approve/reject/kill** |
| Creative body fuzz | Gap | Gap | **Phase 3 rigorous** |

**Stack position:** NeMo/Bedrock (safety) → **Ad Guard** (spend) → DSP + DV/IAS (placement)

---

## 7 — Health Telemetry

**One job:** Device batch **tamper evidence** — schema + sequence gate + optional WAL ingress, HIPAA diligence pack, **not FDA cert**.

**Pitch:** *Prove telemetry batches weren't altered — without buying an EMR.*

### Competitive comparison (capability)

| Capability | Cloud IoT hub | Spreadsheet export | **Health Telemetry** |
|------------|---------------|-------------------|---------------------|
| Per-device sequence gate | Typical | None | **Fail-closed** |
| Device auth HTTP | Typical | N/A | **Phase 3 rigorous** |
| Observation-lane export | Gap | N/A | **Proven verify chain** |
| Offline verify | No | No | **verify-bundle** |
| FDA / device cert | Sometimes | N/A | **Explicit non-goal** |

---

## 8 — ModelGovernor

Two surfaces — diligence treats them separately:

| Surface | Buyer | Demo |
|---------|-------|------|
| **8a Lifecycle CLI** | Model risk, MLOps, regulated lending | `demo_model_governor.sh` |
| **8b LLM spend plane** | Platform eng, FinOps | `make demo-gold` |

**Pitch (lifecycle):** *Prove which model version was approved for production on date X.*  
**Pitch (spend plane):** *LiteLLM governs traffic; Spend Guard governs money.*

### 8a — Lifecycle competitive comparison

| Capability | MLflow Registry | GRC SaaS | **ModelGovernor** |
|------------|-----------------|----------|-------------------|
| Model snapshot contract | Tags/params | Custom fields | **First-class + artifact_hash** |
| Approve/deploy audit | Version history | Case workflow | **Genesis per event** |
| Offline verify | Needs server | No | **verify-bundle** |
| Drift as sealed event | Metrics only | Ticket | **`drift_alert` on chain** |

### 8b — Spend plane (canonical demo)

```bash
make demo-gold-up
make demo-gold          # 11 steps — drift lockout step 10
make demo-gold-reset    # before rerun after lockout
```

| vs category | They do well | Inst++ differentiator |
|-------------|--------------|----------------------|
| AI gateway (LiteLLM, Portkey) | Route, keys, budgets | Reserve → settle → drift lockout + genesis audit |
| LLM observability (Langfuse) | Traces, evals | Block spend before inference; wallet semantics |
| Cloud FinOps | Infra chargeback | Per-request LLM governance at gateway |

---

## 9 — Drift Gate

**One job:** PSI/KS statistical drift interceptor — shadow burn-in, then enforce reject/kill with genesis audit.

**Pitch:** *Block drifted inference before the regulator calls — with math, not a dashboard.*

### Competitive comparison (capability)

| Capability | Evidently / Fiddler | WhyLabs | **Drift Gate** |
|------------|---------------------|---------|----------------|
| PSI + KS per feature | Typical | Typical | **Proven rigorous** |
| Shadow → enforce | Partial (alerts) | Partial | **Inline block** |
| Proxy hot-path | Gap | Gap | **#2 integration** |
| Genesis audit per eval | Gap | Partial | **Yes** |
| Offline verify | Gap | Gap | **verify-bundle** |

---

## 10 — Webhook Replay

**One job:** Capture raw webhook ingress bytes, replay offline without network, prove idempotent outcomes with genesis audit.

**Pitch:** *Replay the exact bytes — prove the second delivery did not double-charge.*

### Competitive comparison (capability)

| Capability | Hookdeck replay | Custom scripts | **Webhook Replay** |
|------------|-----------------|----------------|-------------------|
| Byte-identical `.wrcap` | Partial | Rare | **Proven** |
| Offline replay | SaaS-dependent | DIY | **No network** |
| Genesis audit on replay | Gap | Gap | **verify-bundle** |

Pairs with **#5 Webhook Mesh** for capture → replay → verify chain.

---

## 11 — Spend Guard

**One job:** Reserve-before-dispatch API spend wallet — hold budget before upstream clears, settle on actual cost, lock on spend drift.

**Pitch:** *LiteLLM governs traffic; Spend Guard governs money.*

### Wallet semantics

| Step | Behavior |
|------|----------|
| Reserve | Hold estimated cost before upstream dispatch |
| Settle | Release hold; debit actual vs estimate |
| Drift lockout | `DRIFT_THRESHOLD_EXCEEDED` → wallet frozen |
| Gateway | OpenAI-compat `/v1/chat/completions` |

### Competitive comparison (capability)

| Capability | LiteLLM budgets | Cloud org limits | **Spend Guard** |
|------------|-----------------|------------------|-----------------|
| Reserve before dispatch | Partial | Gap | **SQLite IMMEDIATE / Postgres** |
| Settle actual vs estimate | Partial | Gap | **Proven** |
| Drift lockout | Gap | Gap | **demo-gold step 10** |
| Genesis spend events | Gap | Gap | **verify-bundle** |

### Tech proof

```bash
make demo-gold
spend-guard verify-bundle --tarball ./data/demo/spend_guard_bundle.tar
```

| Layer | Status | Detail |
|-------|--------|--------|
| Institutional gold | ✅ | Rigorous: idempotency, API key, drift lock |
| Production | ✅ | Single-instance SQLite wallet; scale: Postgres profile optional |
| CI | ✅ | `spend_guard` rigorous — PASSED |

---

## 12 — Agent Ledger

**One job:** Fail-closed runtime governance for AI agent tool calls — prove which actions were permitted, denied, or escalated *before* execution.

**Pitch:** *ModelGovernor proves which model was approved. Agent Ledger proves which tools actually ran.*

### vs ModelGovernor

| ModelGovernor (#8) | Agent Ledger (#12) |
|--------------------|-------------------|
| Model artifact lifecycle | Runtime tool authorization |
| SR 11-7 / model risk evidence | SOC2 / agent security |
| “Who signed off model v3.2.1?” | “Who permitted this transfer before the agent ran it?” |

### Competitive comparison (capability)

| Capability | LangSmith policies | Oso / OPAL | **Agent Ledger** |
|------------|-------------------|------------|------------------|
| Authorize before invoke | Partial | Typical | **Proven** |
| Deny / escalate fail-closed | Partial | Typical | **Explicit rigorous pass** |
| Human attestation | Gap | Partial | **escalation lane** |
| Offline verify | Gap | Gap | **verify-bundle** |

---

## Vertical bundles (logical, not separate SKUs)

| Bundle | SKUs | Job |
|--------|------|-----|
| **Finance Governor** | #11 + #9 (+ #2 optional) | LLM/API spend + drift enforce + outbound firewall |
| **Insurance Governor** | #8 + #9 + #1 | Model lifecycle + drift + decision audit |
| **Agent stack** | #12 + #4 + #11 | Tool auth + trace + spend |
| **Billing integrity** | #5 + #10 | Ingress idempotency + forensic replay |
| **Full spine** | All 12 | One `PORTFOLIO_MANIFEST.json` over 12 verify-bundle |

---

## Diligence (15 minutes)

```bash
pip install -e ".[dev,instpp]"
make plug                              # demo-all + verify 12/12
./scripts/instpp_smoke_test.sh
./scripts/instpp_rigorous_test.sh
make docker-extended                   # when Docker available
make demo-gold                         # spend plane walkthrough
cat docs/test_logs/instpp_rigorous_latest_summary.json
```

**Evidence packs:** [BUYER_EVIDENCE_PACK.md](BUYER_EVIDENCE_PACK.md) · [SOC2_VPC_DILIGENCE_PACK.md](SOC2_VPC_DILIGENCE_PACK.md)

---

## Pilot ladder (process, not pricing)

| Stage | Duration | Deliverable |
|-------|----------|-------------|
| Dry-run | 1 meeting | Demo + `verify-bundle` on sample tarball |
| Shadow | 2–4 weeks | VPC deploy, shadow mode (#2, #6) or read-only (#3) |
| Live pilot | 4–8 weeks | Single tenant, one route/feed/ward |
| Production | — | VPC deploy + maintenance (procurement offline — not in repo) |

---

## Related documents (diligence pack)

| Doc | Purpose |
|-----|---------|
| [INST_PLUS_DILIGENCE_PACK.md](INST_PLUS_DILIGENCE_PACK.md) | Pack index — start here |
| [PORTFOLIO_EVIDENCE_SHEET.md](PORTFOLIO_EVIDENCE_SHEET.md) | Per-SKU proof commands and CI artifacts |
| [INST_PLUS_PLATFORM_COMPARE.md](INST_PLUS_PLATFORM_COMPARE.md) | Capability matrix vs adjacent platforms |
| [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) | Nine dimensions bar |
| [BUYER_EVIDENCE_PACK.md](BUYER_EVIDENCE_PACK.md) | 15-minute auditor dry-run |
| [docs/test_logs/README.md](test_logs/README.md) | Committed CI evidence |
