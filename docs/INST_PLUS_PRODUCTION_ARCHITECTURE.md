# Institutional++ Production Architecture

**Purpose:** Industry-standard map of architecture, code execution paths, and production readiness criteria for all 12 SKUs.  
**Audience:** Platform engineering, InfoSec, procurement diligence.  
**Date:** July 2026

---

## Production readiness definition

| Layer | Meaning | Gate |
|-------|---------|------|
| **Institutional gold** | F1–F9 + `verify-bundle` + rigorous E2E | CI `instpp_rigorous_test.sh` per SKU |
| **Production (single-instance VPC)** | Air-gap SQLite + WAL, HTTP `/health` + `/ready` (where served), CLI export path | No Redis/Postgres required |
| **Scale profile** | Multi-replica HA | `INST_PRODUCTION_PROFILE=1` + Redis streams / Postgres — see [PRODUCTION_REDIS_PROFILE.md](PRODUCTION_REDIS_PROFILE.md) |

**Prod ✅** in the completion matrix means **single-tenant VPC envelope complete**. Redis, Postgres, and buyer-specific feed integrations are **scale or SOW items**, not license blockers.

---

## Spine architecture (all SKUs)

```mermaid
flowchart TB
  subgraph ingress [Ingress]
    HTTP[HTTP serve / CLI / integrate hook]
    WAL[WAL fsync where applicable]
  end
  subgraph spine [inst_spine]
    LEDGER[AppendOnlyLedger SQLite WAL]
    GATES[F1-F9 institutional check]
    EXPORT[build_audit_bundle + HMAC sidecar]
    VERIFY[verify-bundle offline]
  end
  subgraph diligence [Diligence]
    PROOF[Proof Console :8790]
    DEMO[make demo-all / per-SKU scripts]
  end
  HTTP --> WAL
  WAL --> LEDGER
  LEDGER --> GATES --> EXPORT --> VERIFY
  DEMO --> LEDGER
  PROOF -->|guided ingest #3-12| LEDGER
  PROOF --> GATES --> EXPORT --> VERIFY
```

Shared libraries: `inst_spine` (ledger, clocks, export, production profile), `inst_workflow` (Proof Console catalog + guided ingest).

---

## Per-SKU execution map

| # | SKU | Ingress | Ledger writer | HTTP serve | CLI | Integrate hook |
|---|-----|---------|---------------|------------|-----|----------------|
| 1 | Compliance Logger | `compliance_log/ingest.log_decision` | `compliance.sqlite` | `:8785` | `compliance-log` | — |
| 2 | Proxy-Risk | `proxy_risk/router.ProxyRiskGateway.evaluate` | `proxy_risk_ledger.sqlite` | `:8786` | `proxy-risk` | middleware |
| 3 | Alt-Data | `altdata/poll.poll_once` | `altdata.sqlite` | `:8787` | `altdata` | feed poll worker |
| 4 | AI Kit | `ai_kit/pipeline.AgentLoop.run_steps` | `ai_kit_trace.sqlite` | — | `ai-kit` | agent runtime |
| 5 | Webhook Mesh | HMAC ingress → WAL → queue | `webhook_mesh.sqlite` | `:8787` | `webhook-mesh` | ingress handler |
| 6 | Ad Guard | `ad_guard/proxy.AdGuardGateway.evaluate` | `ad_guard.sqlite` | `:8788` | `ad-guard` | spend gate |
| 7 | Health Telemetry | `health_telemetry/ingest.ingest_batch` | `health.sqlite` | `:8793` | `health-telemetry` | device gateway |
| 8a | ModelGovernor | `model_governor/record.record_governance_event` | `model_governor.sqlite` | — | `model-governor` | deploy gate |
| 9 | Drift Gate | `drift_gate/integrate.evaluate_model_features` | `drift_gate.sqlite` | — | `drift-gate` | proxy / MG hook |
| 10 | Webhook Replay | `webhook_replay/replay_engine.ReplayEngine` | `webhook_replay.sqlite` | — | `webhook-replay` | mesh capture |
| 11 | Spend Guard | `spend_guard/gateway.SpendGuardGateway` | `spend_guard.sqlite` | `:8789` | `spend-guard` | LLM gateway |
| 12 | Agent Ledger | `agent_ledger/integrate.authorize_tool_call` | `agent_ledger.sqlite` | `:8792` | `agent-ledger` | LangChain hook |

---

## Proof Console guided ingest (#3–#12)

**Module:** `src/inst_workflow/proof_ingest.py`  
**API:** `GET /api/proof/{id}/demo-payload` · `POST /api/proof/{id}/ingest`

| SKU | Demo action | Offline-safe |
|-----|-------------|--------------|
| Alt-Data | `poll_once` stub feed | ✅ |
| AI Kit | AgentLoop stub steps | ✅ |
| Webhook Mesh | Cold-path ingress ledger append | ✅ |
| Ad Guard | Shadow `evaluate` | ✅ |
| Health | `ingest_batch` + auto seq | ✅ |
| ModelGovernor | `record_governance_event` | ✅ |
| Drift Gate | Synthetic baseline + shadow evaluate | ✅ |
| Webhook Replay | capture → replay | ✅ |
| Spend Guard | init wallet → reserve → settle | ✅ |
| Agent Ledger | authorize / complete | ✅ |

Compliance (#1) and Proxy (#2) retain full workflows on the Architecture tab.

---

## Single-instance `/ready` criteria

Without `INST_PRODUCTION_PROFILE=1`:

| SKU | `/ready` requires |
|-----|-------------------|
| Proxy-Risk | Ledger file + chain (shadow: memory backends OK) |
| Alt-Data | Ledger file + chain |
| Webhook Mesh | `WEBHOOK_PROVIDER_SECRET`, WAL online, background queue |
| Ad Guard | Ledger file + chain (shadow) |
| Health Telemetry | Ledger file + chain |
| Spend Guard | Wallet + ledger files, wallet readable |
| Agent Ledger | Ledger + permit DB + chain |
| inst-workflow | 12/12 portfolio DBs seeded |

Rigorous proof: `tests/test_sku_production_envelope.py`

---

## Scale profile (optional)

When `INST_PRODUCTION_PROFILE=1` or multi-instance deploy:

| SKU | Additional requirement |
|-----|------------------------|
| #2, #6 | `INST_REDIS_URL` — token bucket + idempotency CAS |
| #5 | `WEBHOOK_DISPATCH_MODE=redis` — durable stream queue |
| #9 | Redis rolling windows for enforce at scale |
| #11 | Postgres wallet when `INST_REQUIRE_POSTGRES=1` |
| #3 | Buyer feed URLs — integration SOW (not spine gap) |

---

## Demo & diligence commands

```bash
make demo-all                    # Seed all 12 portfolio DBs
make demo-gold-up                # Proof Console :8790
./scripts/instpp_proof_lite.sh  # Production profile + portfolio verify
./scripts/instpp_smoke_test.sh   # Fast regression
```

**Diligence pack index:** [INST_PLUS_DILIGENCE_PACK.md](INST_PLUS_DILIGENCE_PACK.md)
