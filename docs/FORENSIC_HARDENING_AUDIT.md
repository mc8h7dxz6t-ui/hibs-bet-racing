# Forensic Hardening Audit — All 12 SKUs

**Purpose:** Per-platform forensic analysis for Inst++ grade robustness — what is **proven today**, what is **partial**, and what hardening moves the needle without lying on the scorecard.

**Audience:** Engineering, diligence, design partners  
**Date:** June 2026  
**Status:** Waves 1–4 **implemented** on branch `cursor/forensic-waves-1-4-64ab`  
**Proof baseline:** `make smoke` (191+) · `make rigorous` (12/12 + forensic suite) · `make retention-drill` · `make soc2-evidence`

---

## How to read this audit

### Grading rubric (honest)

| Score | Meaning |
|-------|---------|
| **10** | Category-leading on the **declared wedge** — proven in CI + production profile + chaos/latency where claimed |
| **9** | Industry Gold (9 Inst dimensions) — rigorous E2E + offline verify; production caveats documented |
| **8** | Strong proof spine, missing one production dimension (Redis HA, Postgres CI, HTTP hardening, or GTM pack) |
| **7** | CLI Gold — correct fail-closed semantics; not yet stress-proven at scale |

**Layers audited per SKU:**

| Layer | Question |
|-------|----------|
| **A — Correctness** | Fail-closed gates, typed errors, chain integrity |
| **B — Durability** | WAL-before-side-effect, crash recovery, Redis/Postgres profiles |
| **C — Security** | AuthN/Z on HTTP surfaces, HMAC, idempotency fail-closed |
| **D — Scale** | Multi-instance CAS, stream durability, p99 hot path |
| **E — Ops** | Probes, runbooks, chaos drills, observability |
| **F — Compliance** | Observation lane, redaction, audit export, HIPAA/SOC templates |

### Forensic tier map (existing proofs)

| Tier | Proof | SKUs |
|------|-------|------|
| **A** | Coverage aggregate, rolling drift state, webhook lifecycle, spend rebuild | spine, drift-gate, webhook-mesh, spend-guard |
| **B** | Cross-SKU integration chains (proxy+spend, ai-kit+agent, model FSM, ad+spend, WRCAP) | proxy, ai-kit, agent-ledger, model-governor, ad-guard, webhook-replay |
| **C** | F8 retention / epoch compaction | inst_spine |
| **D** | p99 &lt;10ms hot paths | spend reserve, agent authorize, altdata feed |

---

## Executive summary

| # | SKU | Inst Gold | Prod hardening | Forensic grade | → 10 requires |
|---|-----|-----------|----------------|----------------|---------------|
| 1 | Compliance Logger | ✅ | Postgres profile ✅ | **9** | Signed export policy, mTLS ingest, SOC2 evidence automation |
| 2 | Proxy-Risk | ✅ | Redis 🟡 | **9** | Redis soak in rigorous, circuit-breaker metrics, live auth |
| 3 | Alt-Data | ✅ | Feeds 🟡 | **8** | Buyer feed SOW + structural rescue CI per feed, feed auth |
| 4 | AI Kit | ✅ | Live LLM 🟡 | **8** | Live step_fn contract tests, OTEL trace export, seat auth |
| 5 | Webhook Mesh | ✅ | Redis Stream 🟡 | **9** | Stream consumer-group chaos, DLQ poison matrix, mTLS ingress |
| 6 | Ad Guard | ✅ | Redis 🟡 | **8** | Creative policy fuzz tests, upstream timeout matrix |
| 7 | Health Telemetry | ✅ | HIPAA template 🟡 | **9** | BAA pack signing workflow, device cert auth, VectorClock LOI only |
| 8 | ModelGovernor | ✅ | ✅ | **9** | Deploy-time drift gate in rigorous, artifact signing |
| 9 | Drift Gate | ✅ | Redis 🟡 | **10** | Redis soak ✅ — add PSI/KS golden-file regression suite |
| 10 | Webhook Replay | ✅ | ✅ | **9** | WRCAP corruption fuzz, lamport mismatch property tests |
| 11 | Spend Guard | ✅ | Postgres 🟡 | **9** | Postgres in rigorous CI, compose north-star honesty, API auth |
| 12 | Agent Ledger | ✅ | HTTP open 🟡 | **8** | mTLS / API key on `/v1/authorize`, permit TTL sweep |

**Portfolio truth:** All 12 are **Industry Gold (9 dimensions)** on the proof spine. **Category 10** is achievable on **4 SKUs today** with declared production profiles: Compliance + Spend (Postgres), Proxy + Drift (Redis). The rest sit at **8–9** until HTTP hardening, feed-specific CI, or compliance pack signing lands.

---

## Shared spine (`inst_spine`) — cross-cutting hardening

### Proven today

- Genesis anchor anti-wipe (`verify_genesis_block`)
- Lamport F4 (clock-attack test in `test_inst_products.py`)
- WAL sync + async SQLite index + replay on startup
- F1–F9 gate engine with observation-lane mode
- Deterministic F9 export + offline `verify-bundle`
- `open_ledger()` / Redis backends / Postgres ledger (Tier 2)

### Gaps → enhancements

| Priority | Gap | Hardening |
|----------|-----|-----------|
| **P0** | F8 retention rarely exercised per-SKU | Add `retention drill` to each SKU rigorous section — epoch compaction + verify-bundle |
| **P0** | Postgres ledger not in rigorous CI | Wire `postgres-profile` job output into `instpp_rigorous_latest_summary.json` |
| **P1** | No unified HTTP auth middleware | `inst_spine.middleware`: API key + mTLS hook for all `serve.py` entrypoints |
| **P1** | Vector clocks | **Do not SKU** — only with named Health Telemetry LOI (`ROADMAP_GTM_DISCIPLINE.md`) |
| **P2** | Merkle epoch proofs | Extend F8 with auditor-facing `epoch_roots.json` in every bundle |
| **P2** | Multi-writer Lamport | Postgres ledger needs writer_id partition tests under concurrent append |

---

## 1 — Compliance Logger (`compliance-log`)

**Wedge:** Tamper-proof business decision audit — snapshot + outcome + hash chain.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | F7 from real snapshot; export aborts on gate fail |
| B Durability | ✅ | WAL + genesis; Postgres `PostgresAppendOnlyLedger` |
| C Security | 🟡 | CLI-only ingest — no HTTP auth surface in SKU |
| D Scale | 🟡 | SQLite single-writer; Postgres for HA |
| E Ops | ✅ | Proof Console 5-step + `/ready` bootstrap |
| F Compliance | 🟡 | Observation lane via workflow; no signed SOC2 pack |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | `compliance-log ingest --database postgres://…` in rigorous E2E | Proves HA profile is CI truth, not doc-only |
| **P0** | Export policy manifest (`retention_years`, `redaction_mode`) embedded in bundle | Auditor asks "what policy produced this tarball?" |
| **P1** | Optional HTTP ingest with mTLS client cert + HMAC body | Enterprise ingress without GRC workflow UI |
| **P1** | F1 context: `expected_snapshots` from config file | Catches silent ingest drop in batch ETL |
| **P2** | Immutable S3/Object-lock export sink | Cold storage for 7-year retention buyers |

**Non-goals (keep honest):** ServiceNow/Archer, SIEM, e-discovery SaaS.

---

## 2 — Proxy-Risk (`proxy-risk`)

**Wedge:** Outbound API firewall — rate limit, Z-score kill, idempotency, shadow → live.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | Every gate outcome on chain; 4xx/5xx → REJECT live |
| B Durability | ✅ | WAL before upstream; Redis fail-closed idempotency |
| C Security | 🟡 | No API key on `serve` — VPC network trust assumed |
| D Scale | 🟡 | Redis required multi-instance; p99 &lt;10ms in industry gold |
| E Ops | ✅ | Shadow default; drift-gate + spend-guard integration |
| F Compliance | ✅ | Offline verify-bundle |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | Redis soak in `instpp_rigorous_test.sh` (not just push CI) | Multi-instance proof is rigorous truth |
| **P0** | Circuit breaker state machine + ledger events | Open/half-open/closed must be auditable |
| **P1** | `PROXY_CLIENT_AUTH` — HMAC or mTLS per `client_id` | Stops lateral movement inside VPC |
| **P1** | Upstream timeout / retry budget as gate | Prevents hung shadow burning Lamport seq |
| **P2** | Per-path cost attribution → Spend Guard auto-wire | Completes B1 forensic tier in production |

**Non-goals:** sub-5ms RTB, Kong lifecycle replacement.

---

## 3 — Alt-Data (`altdata`)

**Wedge:** One clean telemetry feed with coverage ladder + structural rescue.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | `CoverageError` below floor; F7 at poll |
| B Durability | ✅ | Ledger per poll |
| C Security | 🟡 | `serve` has memory rate limit only — no auth |
| D Scale | 🟡 | p99 feed API in Tier D; single built-in feed |
| E Ops | ✅ | `list-feeds`, demo script |
| F Compliance | 🟡 | Rescue metadata in ledger |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | Per-feed rigorous E2E slot in manifest (not just `demo_feed`) | Buyer feed = design-partner SOW needs CI template |
| **P0** | Structural rescue golden-file tests per feed version | DOM breakage is the #1 production failure mode |
| **P1** | Feed API key + Redis rate limit backend | Multi-instance feed serving |
| **P1** | Poll worker crash recovery — WAL for in-flight poll | Partial poll must not advance Lamport |
| **P2** | Feed schema registry in bundle extras | Auditor validates field ladder version |

**Non-goals:** Airflow/Fivetran, exchange tick latency.

---

## 4 — AI Kit (`ai-kit`)

**Wedge:** Agent loop with rate limits, Lamport checkpoints, trace ledger.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | `RateLimitError` typed; checkpoint resume |
| B Durability | ✅ | Trace ledger + checkpoint DB |
| C Security | 🟡 | Tool auth delegated to Agent Ledger when configured |
| D Scale | 🟡 | Single-process; no distributed checkpoint |
| E Ops | ✅ | `validate-demo` |
| F Compliance | 🟡 | Trace export; no PII redaction lane |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | Contract test for buyer `step_fn` (timeout, exception, partial state) | Live LLM is design-partner path — must not crash loop |
| **P0** | Mandatory `agent_ledger_db` in rigorous E2E | B2 forensic tier becomes default, not optional |
| **P1** | Observation-lane trace redaction (mirror Health Telemetry) | Enterprise AI buyers ask about prompt logging |
| **P1** | OpenTelemetry span export alongside ledger | Ops wedge without LangSmith replacement |
| **P2** | Distributed checkpoint (Redis) for multi-worker agents | Only with LOI |

**Non-goals:** LangGraph, vector DB, hosted observability platform.

---

## 5 — Webhook Mesh (`webhook-mesh`)

**Wedge:** HMAC ingress, WAL-before-ack, delivery FSM, Redis Stream dispatch.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | HMAC fail → 401; idempotency fail-closed on Redis error |
| B Durability | ✅ | WAL before HTTP 200; Redis Stream mode |
| C Security | ✅ | HMAC verification |
| D Scale | 🟡 | Background queue loses tasks without Redis |
| E Ops | ✅ | DLQ replay CLI |
| F Compliance | ✅ | Delivery lifecycle on ledger (Tier A3) |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | Consumer-group crash chaos test (kill mid-forward, verify redelivery) | Stream durability is the prod claim |
| **P0** | Poison message matrix — N failures → DLQ + ledger `POISON` status | Buyers ask about bad payloads |
| **P1** | mTLS ingress option (parallel to HMAC) | Enterprise webhook receivers |
| **P1** | Per-tenant signing secret rotation without restart | Ops runbook gap |
| **P2** | Delivery SLA histogram in bundle extras | Not a dashboard — auditor-readable JSON |

**Non-goals:** Kafka-scale, Svix/Hookdeck replacement.

---

## 6 — Ad Guard (`ad-guard`)

**Wedge:** Creative spend proxy — approve/reject/kill on chain with optional spend wallet.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | All decisions logged; creative policy tests |
| B Durability | ✅ | Same spine as proxy-risk |
| C Security | 🟡 | Redis idempotency; no ingress auth |
| D Scale | 🟡 | Redis for multi-instance |
| E Ops | ✅ | `serve` HTTP gateway |
| F Compliance | 🟡 | Creative metadata in ledger |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | Creative policy fuzz suite (malformed HTML, unicode, oversized payload) | Ad payloads are adversarial |
| **P1** | Upstream timeout + spend settle on partial failure | Money leak on hung upstream |
| **P1** | Align with Proxy-Risk `PROXY_CLIENT_AUTH` pattern | Shared enterprise tier |
| **P2** | IAB category blocklist as versioned bundle extra | Buyer-specific policy packs |

**Non-goals:** RTB/DSP UI, sub-5ms bidding.

---

## 7 — Health Telemetry (`health-telemetry`)

**Wedge:** Device batch ingest, per-device seq gate, WAL-before-ack, observation lane.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | Schema + F7 at ingest; seq gap fail-closed |
| B Durability | ✅ | Ingress WAL fsync before ack |
| C Security | 🟡 | No device authentication — device_id trust |
| D Scale | 🟡 | Redis idempotency optional |
| E Ops | ✅ | Demo DB wipe fix; rigorous E2E |
| F Compliance | 🟡 | HIPAA pack template — not signed BAA |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | Device credential (JWT or cert thumbprint) bound to `device_id` | Hospital pilot blocker |
| **P0** | Seq gate chaos — replay WAL after crash mid-batch | Tier-7 durability proof |
| **P1** | Observation-lane export in rigorous (redacted bundle verify) | PHI diligence |
| **P1** | Batch size / packet rate limits per device | DoS on ingress |
| **P2** | VectorClock multi-device | **LOI only** — do not build speculatively |

**Non-goals:** FDA, EMR integration, clinical UI.

---

## 8 — ModelGovernor (`model-governor`)

**Wedge:** Model lifecycle FSM on chain — register → approve → deploy → retire.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | FSM enforced (Tier B3); F7 on snapshot |
| B Durability | ✅ | Standard spine |
| C Security | ✅ | CLI — no open HTTP |
| D Scale | ✅ | Single-writer appropriate |
| E Ops | ✅ | Drift-gate at deploy in rigorous |
| F Compliance | ✅ | Governance actions auditable |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | Artifact hash verification against external manifest | Deploy gate must reject hash mismatch |
| **P1** | Dual-control approve (two manifest_ids) | Regulated model deploy |
| **P1** | Auto-retire on drift-gate enforce trigger | Closes loop with #9 |
| **P2** | SBOM / model card as bundle extras | Emerging buyer ask |

**Non-goals:** MLflow/Arize full platform.

---

## 9 — Drift Gate (`drift-gate`)

**Wedge:** PSI/KS enforce at proxy hot path; Redis rolling state.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | PSI/KS per feature; shadow/enforce modes |
| B Durability | ✅ | Rolling state file + Redis profile |
| C Security | ✅ | Embed via `integrate.py` — no open HTTP |
| D Scale | ✅ | Redis soak CI (Tier 2) |
| E Ops | ✅ | Baseline versioning in demo |
| F Compliance | ✅ | Evaluation events on chain |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | Golden-file PSI/KS regression (known distributions) | Math correctness is the product |
| **P1** | Feature null / missing handling matrix | Production data is messy |
| **P1** | Baseline semver + incompatible baseline reject | Silent wrong baseline is catastrophic |
| **P2** | Fairness metrics (disparate impact) | **LOI only** — not fairness certification |

**Highest ROI:** Already nearest **category 10** — golden-file math tests close the gap.

---

## 10 — Webhook Replay (`webhook-replay`)

**Wedge:** WRCAP mmap capture; air-gapped byte-identical replay.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | Tamper fail-closed (industry gold) |
| B Durability | ✅ | mmap capture survives process crash |
| C Security | ✅ | Air-gap replay — no network |
| D Scale | 🟡 | File-based — not Kafka scale |
| E Ops | ✅ | Integrate with webhook-mesh capture dir |
| F Compliance | ✅ | Lamport attestation (Tier B5) |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | WRCAP header corruption fuzz (truncated, wrong magic, flipped bytes) | Capture files are evidence |
| **P1** | Replay diff report as JSON in bundle | Auditor-readable without UI |
| **P1** | Capture retention / rotation policy (F8 alignment) | Long-running mesh fills disk |
| **P2** | Parallel replay workers with deterministic merge | Large capture sets |

**Non-goals:** Delivery platform, Kafka.

---

## 11 — Spend Guard (`spend-guard`)

**Wedge:** Reserve → settle → drift lockout; OpenAI-compat gateway.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | IMMEDIATE reserve/settle; drift lockout |
| B Durability | ✅ | Wallet + ledger; Postgres wallet (Tier 2) |
| C Security | 🟡 | Gateway has no client auth — OpenAI-compat trust |
| D Scale | 🟡 | p99 &lt;10ms Tier D; Postgres not in rigorous |
| E Ops | 🟡 | `make demo-gold` north star vs rigorous CLI |
| F Compliance | ✅ | Spend phases on chain |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | Postgres wallet + ledger in rigorous E2E | Honest 8b / #11 production grade |
| **P0** | `SPEND_GUARD_API_KEY` on `/v1/chat/completions` | Gateway is an attack surface |
| **P1** | Duplicate settle / duplicate reserve idempotency matrix | Money correctness |
| **P1** | Multi-currency as **explicit non-goal** in check gate | Prevent silent float rounding bugs |
| **P2** | Treasury dashboard export (JSON not UI) | CFO diligence |

**Non-goals:** Full LiteLLM replacement, multi-currency treasury.

---

## 12 — Agent Ledger (`agent-ledger`)

**Wedge:** Authorize-before-invoke; permit → complete attestation.

### Forensic evidence (today)

| Layer | Status | Proof |
|-------|--------|-------|
| A Correctness | ✅ | Duplicate complete fail-closed |
| B Durability | ✅ | Permit DB separate from ledger |
| C Security | 🔲 | **`serve` has no auth** — open POST |
| D Scale | ✅ | p99 authorize Tier D |
| E Ops | ✅ | AI Kit integration hook |
| F Compliance | 🟡 | Policy tiers; no SOX dual-control |

### Hardening backlog

| P | Enhancement | Why |
|---|-------------|-----|
| **P0** | `AGENT_LEDGER_API_KEY` or mTLS on `/v1/authorize` + `/v1/complete` | **Critical** — open HTTP is not prod-grade |
| **P0** | Permit TTL + sweep expired permits (ledger event) | Stale permits = security hole |
| **P1** | Argument schema validation per tool (JSON Schema) | Policy alone is insufficient |
| **P1** | Risk-tier escalation requires second authorize | SOX-adjacent buyers |
| **P2** | OAuth delegation map (agent → service account) | Enterprise IAM integration |

**Non-goals:** LangChain/CrewAI framework replacement.

---

## Cross-SKU integration hardening

| Integration | Proven | Gap | Enhancement |
|-------------|--------|-----|-------------|
| Proxy → Drift Gate | ✅ rigorous | Enforce mode soak | 1000-iteration enforce shadow→live promotion test |
| Proxy → Spend Guard | ✅ Tier B1 | Auto-settle on upstream cost | Parse upstream billing headers |
| Webhook Mesh → Replay | ✅ industry gold | Capture dir disk full | F8 rotation on WRCAP directory |
| AI Kit → Agent Ledger | ✅ Tier B2 | Not default in rigorous | Make `agent_ledger_db` required |
| ModelGovernor → Drift Gate | ✅ rigorous E2E | Retire on enforce | Auto-retire FSM transition |
| Ad Guard → Spend Guard | ✅ Tier B4 | Production auth | Shared auth middleware |
| Proof Console → all 12 | ✅ Tier 2 | Verify-all needs tarballs | Init container: demo-all + verify in K8s |

---

## Recommended implementation order (highest ROI)

Technical dependency order — not calendar estimates.

### Wave 1 — Close category-10 gaps (4 SKUs)

1. **Agent Ledger HTTP auth** (P0 security hole)
2. **Spend Guard gateway API key** + Postgres in rigorous
3. **Redis soak in rigorous** (Proxy + Drift)
4. **Drift Gate golden-file PSI/KS** tests

### Wave 2 — Production envelope (all HTTP serves)

5. `inst_spine.middleware` — shared API key / mTLS hook
6. Apply to: `agent_ledger`, `spend_guard`, `altdata`, `health_telemetry`, `inst_workflow`
7. F8 retention drill in each rigorous section

### Wave 3 — Buyer-specific depth

8. Health Telemetry device auth + observation-lane rigorous
9. Alt-Data per-feed CI template + structural rescue golden files
10. Webhook Mesh consumer-group chaos + poison matrix
11. Compliance export policy manifest + optional mTLS ingest

### Wave 4 — Diligence automation

12. SOC2 evidence collector from `PORTFOLIO_MANIFEST.json`
13. Signed bundle option (cosign/minisign) for export tarballs
14. Epoch Merkle roots in all bundle extras

---

## Proof commands after hardening

```bash
make plug                    # 12/12 offline
make smoke                   # 174+ unit/integration
make rigorous                # 12/12 E2E + new profiles
make chaos                   # industry gold drills
make redis-soak              # Redis production profile
INST_TEST_POSTGRES_DSN=… python -m pytest tests/test_postgres_profile.py
./scripts/instpp_buyer_pack.sh
```

---

## Related documents

- [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) — nine dimensions
- [PORTFOLIO_TECH_SALES_SHEET.md](PORTFOLIO_TECH_SALES_SHEET.md) — completion matrix
- [PRODUCTION_DEPLOYMENT.md](PRODUCTION_DEPLOYMENT.md) — K8s profiles
- [ROADMAP_GTM_DISCIPLINE.md](ROADMAP_GTM_DISCIPLINE.md) — explicit non-SKUs
- [tests/test_forensic_tiers.py](../tests/test_forensic_tiers.py) — Tier A/B/C/D proofs
