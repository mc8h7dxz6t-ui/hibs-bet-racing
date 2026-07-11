# Institutional++ Portfolio — Evidence Sheet (12 SKUs)

**Audience:** Technical evaluators, auditors, platform engineering, procurement diligence  
**Posture:** Factual capability and proof only — no Inst++ pricing  
**Scope:** SKU / Inst++ layer only (not sports, trading overlay, or governor consumer apps)  
**Date:** July 2026

> **Diligence pack:** [INST_PLUS_DILIGENCE_PACK.md](INST_PLUS_DILIGENCE_PACK.md)  
> **Full tech/sales:** [PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md](PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md)  
> **Market compare:** [INST_PLUS_PLATFORM_COMPARE.md](INST_PLUS_PLATFORM_COMPARE.md)

---

## What this portfolio is

Twelve deployable infrastructure products share one cryptographic audit spine (`inst_spine`): genesis-anchored hash chains, Lamport clocks, F1–F9 institutional gates, deterministic `export` bundles, and offline `verify-bundle` that an auditor runs without calling the vendor.

Every SKU ships:

- A CLI with fail-closed `InstError` envelopes
- A `scripts/demo_<product>.sh` script (typically under 60 seconds, offline-capable)
- Rigorous E2E coverage in `scripts/instpp_rigorous_test.sh`
- Unit and integration tests in `tests/test_*.py`
- Buyer one-pager in `docs/*_BUYER.md` and technical spec in `docs/*_SALES_TECH_SPEC.md`

---

## Portfolio proof envelope

| Layer | Command / artifact | What it proves |
|-------|-------------------|----------------|
| Plug | `make plug` | Install + demo-all 12/12 + offline verify |
| Smoke | `./scripts/instpp_smoke_test.sh` | 219+ institutional pytest tests |
| Proof-lite (PR) | `./scripts/instpp_proof_lite.sh` | Production profile gates + portfolio verify |
| Rigorous E2E | `./scripts/instpp_rigorous_test.sh` | Per-SKU ingest → gate → export → verify in CI log |
| Full proof | `make proof` | Smoke + rigorous + verify-portfolio |
| Docker extended | `make docker-extended` | Redis + Postgres compose + zero-skip rigorous on host |
| Docker SKU rigorous | `make docker-sku-rigorous` | 12 isolated containers — per-SKU unit + demo + verify logs |
| Buyer pack | `make buyer-pack` | `PORTFOLIO_MANIFEST.json` + bundle tarballs |
| SOC2 evidence | `make soc2-evidence` | VPC evidence JSON from verified manifest |
| Chaos | `./scripts/chaos_instpp.sh` | WAL / wallet / capture survival drills |

**Logged artifacts** (`docs/test_logs/`):

| File | Contents |
|------|----------|
| `instpp_rigorous_latest_summary.json` | PASS/FAIL, `skipped_sections`, forensic waves 1–4 |
| `instpp_proof_lite_latest_summary.json` | PR diligence steps + manifest linkage |
| `instpp_docker_extended_latest_summary.json` | Compose live run + rigorous zero-skip |
| `instpp_docker_sku_latest_summary.json` | Per-SKU docker matrix (12 containers) |
| `instpp_docker_sku_<sku>_latest.log` | Isolated container log per SKU |
| `instpp_ci_autonomy_phases.json` | Phase 1–4 implementation ledger |
| `soc2_evidence_latest.json` | SOC2 VPC evidence collector output |

**CI** (`.github/workflows/instpp-ci.yml`): `smoke`, `proof-lite`, `rigorous`, `proof`, `redis-soak`, `postgres-profile`, `soc2-evidence`, `compose-redis`, `docker-extended` (schedule / workflow_dispatch).

---

## Shared spine (all 12 SKUs)

| Capability | Evidence |
|------------|----------|
| Genesis hash chain + anti-wipe | `inst_spine` WAL; F3–F4 gates |
| Lamport monotonicity | Clock-attack resistance in rigorous + unit tests |
| Deterministic export + SHA256 sidecar | `*-bundle verify-bundle --tarball` |
| Air-gap SQLite + WAL | Default deployment; Postgres optional (#1, #11) |
| F1–F9 institutional check | Per-SKU export manifests |
| Bundle HMAC signing | `INST_BUNDLE_SIGNING_KEY` in rigorous wave 4 |
| Epoch roots in compliance export | Phase 3 rigorous section |
| Production profile fail-closed `/ready` | `tests/test_production_profile_serve_ready.py` |
| Redis stream dispatch | `WEBHOOK_DISPATCH_MODE=redis` + `INST_REDIS_URL` |
| K8s PVC + init bootstrap | `deploy/k8s/pvc-instpp.yaml`, `inst-workflow-deployment.yaml` |

---

## SKU index — what each product does

| # | Product | SKU | One job | Demo | Tech spec |
|---|---------|-----|---------|------|-----------|
| 1 | Compliance Logger | `compliance-log` | Tamper-proof audit trail for regulated approve/deny/escalate decisions | `demo_compliance_logger.sh` | [COMPLIANCE_LOGGER_SALES_TECH_SPEC.md](COMPLIANCE_LOGGER_SALES_TECH_SPEC.md) |
| 2 | Proxy-Risk | `proxy-risk` | Outbound API firewall — rate limit, dedupe, drift kill, audit before upstream | `demo_proxy_risk.sh` | [PROXY_RISK_SALES_TECH_SPEC.md](PROXY_RISK_SALES_TECH_SPEC.md) |
| 3 | Alt-Data | `altdata` | Clean telemetry feed with structural fallback and per-poll proof | `demo_altdata.sh` | [ALTDATA_SALES_TECH_SPEC.md](ALTDATA_SALES_TECH_SPEC.md) |
| 4 | AI Kit | `ai-kit` | Agentic AI trace ledger — rate limits, state, validated JSON | `demo_ai_kit.sh` | [AI_KIT_SALES_TECH_SPEC.md](AI_KIT_SALES_TECH_SPEC.md) |
| 5 | Webhook Mesh | `webhook-mesh` | WAL-before-ack webhook ingress with idempotency and async forward | `demo_webhook_mesh.sh` | [WEBHOOK_MESH_SALES_TECH_SPEC.md](WEBHOOK_MESH_SALES_TECH_SPEC.md) |
| 6 | Ad Guard | `ad-guard` | Marketing API spend guard — Z-score kill, per-campaign bucket | `demo_ad_guard.sh` | [AD_GUARD_SALES_TECH_SPEC.md](AD_GUARD_SALES_TECH_SPEC.md) |
| 7 | Health Telemetry | `health-telemetry` | Device batch ingress with sequence gate and observation-lane export | `demo_health_telemetry.sh` | [HEALTH_TELEMETRY_SALES_TECH_SPEC.md](HEALTH_TELEMETRY_SALES_TECH_SPEC.md) |
| 8 | ModelGovernor | `model-governor` | ML model lifecycle — register, approve, deploy, retire with snapshot hash | `demo_model_governor.sh` | [MODEL_GOVERNOR_SALES_TECH_SPEC.md](MODEL_GOVERNOR_SALES_TECH_SPEC.md) |
| 9 | Drift Gate | `drift-gate` | PSI/KS drift interceptor — shadow burn-in then enforce reject/kill | `demo_drift_gate.sh` | [DRIFT_GATE_SALES_TECH_SPEC.md](DRIFT_GATE_SALES_TECH_SPEC.md) |
| 10 | Webhook Replay | `webhook-replay` | Byte-identical webhook capture and offline replay | `demo_webhook_replay.sh` | [WEBHOOK_REPLAY_SALES_TECH_SPEC.md](WEBHOOK_REPLAY_SALES_TECH_SPEC.md) |
| 11 | Spend Guard | `spend-guard` | Reserve-before-dispatch spend wallet with drift lockout | `demo_spend_guard.sh` · `make demo-gold` | [SPEND_GUARD_SALES_TECH_SPEC.md](SPEND_GUARD_SALES_TECH_SPEC.md) |
| 12 | Agent Ledger | `agent-ledger` | Fail-closed tool authorization before agent execution | `demo_agent_ledger.sh` | [AGENT_LEDGER_SALES_TECH_SPEC.md](AGENT_LEDGER_SALES_TECH_SPEC.md) |

**Buyer one-pagers:** `docs/*_BUYER.md`

---

## Per-SKU evidence (factual)

### 1 — Compliance Logger (`compliance-log`)

| What it does | Records governance decisions on a genesis chain; exports deterministic audit bundles |
| Proof command | `compliance-log verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | ingest, export, verify; mTLS ingest (phase 3); epoch roots on export |
| Key tests | `tests/test_compliance*.py`, `tests/test_phase3_buyer_depth.py` |
| Production options | Postgres ledger when `INST_TEST_POSTGRES_DSN` set |

### 2 — Proxy-Risk (`proxy-risk`)

| What it does | Hot-path gate chain: circuit → schema → token bucket → idempotency → Z-score drift → shadow/live forward |
| Proof command | `proxy-risk verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | shadow mode, live forward (when enabled), client auth, p99 latency bench |
| Key tests | `tests/test_proxy*.py`, industry gold latency assertions |
| Integrations | Drift Gate baseline via `PROXY_DRIFT_BASELINE` |

### 3 — Alt-Data (`altdata`)

| What it does | Polls registered feeds, structural rescue on fetch failure, per-feed registry in rigorous |
| Proof command | `altdata verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | per-feed poll (`fx_gbp_cross`), structural golden rescue |
| Key tests | `tests/test_altdata*.py`, `tests/test_altdata_structural_golden.py` |

### 4 — AI Kit (`ai-kit`)

| What it does | Traces agent steps with `step_fn` contract, rate limits, validated JSON blobs |
| Proof command | `ai-kit verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | agent trace export; step_fn contract (phase 3) |
| Key tests | `tests/test_ai_kit*.py`, `tests/test_phase3_buyer_depth.py` |

### 5 — Webhook Mesh (`webhook-mesh`)

| What it does | HMAC verify → Redis SETNX idempotency → WAL fsync → HTTP 200 → Redis stream forward |
| Proof command | `webhook-mesh verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | ingress, Redis live dispatch, consumer XAUTOCLAIM reclaim, poison DLQ matrix |
| Key tests | `tests/test_webhook*.py`, `tests/test_webhook_mesh_chaos.py`, `tests/test_redis_*.py` |
| Production | `WEBHOOK_DISPATCH_MODE=redis`, `INST_REDIS_URL` |

### 6 — Ad Guard (`ad-guard`)

| What it does | Campaign velocity Z-score kill switch with genesis audit before spend leaves account |
| Proof command | `ad-guard verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | enforce gate (no `|| true` mask); creative body fuzz (phase 3) |
| Key tests | `tests/test_ad_guard*.py`, `tests/test_phase3_buyer_depth.py` |

### 7 — Health Telemetry (`health-telemetry`)

| What it does | Device-authenticated batches, per-device sequence gate, observation-lane export |
| Proof command | `health-telemetry verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | device auth HTTP, obs-lane verify chain, sequence gap fail-closed |
| Key tests | `tests/test_health*.py`, `tests/test_phase3_buyer_depth.py` |

### 8 — ModelGovernor (`model-governor`)

| What it does | Model register/approve/deploy/retire with canonical `artifact_hash` on snapshot |
| Proof command | `model-governor verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | lifecycle demo; artifact hash gate (phase 3); `make demo-mg-gold` walkthrough |
| Key tests | `tests/test_model*.py`, `src/model_governor/integrity.py` |

### 9 — Drift Gate (`drift-gate`)

| What it does | PSI/KS per feature; shadow burn-in; enforce rejects/kills with audit events |
| Proof command | `drift-gate verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | enforce mode (explicit pass); golden PSI/KS; feature null matrix |
| Key tests | `tests/test_drift*.py`, industry gold drift assertions |

### 10 — Webhook Replay (`webhook-replay`)

| What it does | Captures raw `.wrcap` bytes from mesh ingress; replays offline for idempotency proof |
| Proof command | `webhook-replay verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | capture → replay → verify byte identity |
| Key tests | `tests/test_webhook_replay*.py` |

### 11 — Spend Guard (`spend-guard`)

| What it does | Reserve → settle wallet; OpenAI-compat gateway; drift lockout freezes wallet |
| Proof command | `spend-guard verify-bundle --tarball <bundle.tar>` |
| Canonical walkthrough | `make demo-gold` (11 steps including drift lockout) |
| Rigorous sections | wallet idempotency, API key auth, demo-drift-lock, Postgres HTTP gateway |
| Key tests | `tests/test_spend*.py`, `tests/test_postgres_profile.py` |
| Production | Postgres wallet/ledger when `INST_TEST_POSTGRES_DSN` set |

### 12 — Agent Ledger (`agent-ledger`)

| What it does | Authorize → complete attestation for agent tools; deny/escalate fail-closed |
| Proof command | `agent-ledger verify-bundle --tarball <bundle.tar>` |
| Rigorous sections | deny path (explicit pass); HTTP auth; AI Kit integration |
| Key tests | `tests/test_agent*.py`, `tests/test_phase3_buyer_depth.py` |

---

## Rigorous E2E summary shape

After `./scripts/instpp_rigorous_test.sh`, `docs/test_logs/instpp_rigorous_latest_summary.json` reports:

- `status`: `PASSED` / `FAILED`
- `products`: 12 product keys
- `skipped_sections`: honest list when Redis/Postgres/live forward unavailable
- `e2e_sections`: 45 (includes phase 3 buyer-depth sections)
- `industry_gold`: true when all nine dimensions satisfied per SKU
- `forensic_waves`: wave_1–wave_4 boolean matrix (Redis/Postgres flags reflect env)

With `INST_RIGOROUS_FAIL_ON_SKIP=1` (CI main, docker-extended): critical sections must not skip when their dependency env is set.

---

## Docker extended live proof

```bash
make docker-extended
# or
./scripts/instpp_docker_extended_test.sh
```

**Compose profiles:** `redis` + `extended` (Postgres 16) + `inst-workflow` UI on `:8790`

**Host env during run:**

- `INST_REDIS_URL=redis://127.0.0.1:6379/0`
- `INST_TEST_POSTGRES_DSN=postgresql://instpp:instpp@127.0.0.1:5432/instpp_test`
- `WEBHOOK_DISPATCH_MODE=redis`
- `INST_RIGOROUS_FAIL_ON_SKIP=1`

**Steps logged:** proof-lite → smoke → rigorous → redis-soak → postgres pytest → workflow `/health` → SOC2 evidence

**Output:** `docs/test_logs/instpp_docker_extended_<UTC>.log` + `instpp_docker_extended_latest_summary.json`

---

## Industry Gold dimensions (portfolio bar)

See [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md). All 12 SKUs meet:

1. Correctness (fail-closed gates logged)  
2. Failure handling (`InstError` + CLI JSON envelope)  
3. Proof (`export` + offline `verify-bundle`)  
4. Demoability (`demo_<product>.sh`)  
5. Diligence (buyer + sales spec docs)  
6. Strategic legibility (one job + non-goals)  
7. Chaos (WAL/wallet/capture survival)  
8. Latency (documented hot-path p99)  
9. Rigorous E2E (CI-logged section per SKU)

---

## Related documents (diligence pack)

| Doc | Purpose |
|-----|---------|
| [INST_PLUS_DILIGENCE_PACK.md](INST_PLUS_DILIGENCE_PACK.md) | Pack index — start here |
| [PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md](PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md) | Full tech + sales |
| [INST_PLUS_PLATFORM_COMPARE.md](INST_PLUS_PLATFORM_COMPARE.md) | Market compare + comparable pricing |
| [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) | Nine dimensions + readiness matrix |
| [BUYER_EVIDENCE_PACK.md](BUYER_EVIDENCE_PACK.md) | 15-minute auditor dry-run |
| [RUN_DEMO.md](RUN_DEMO.md) | Plug / demo / run guide |
| [docs/test_logs/README.md](test_logs/README.md) | Committed test log index |
