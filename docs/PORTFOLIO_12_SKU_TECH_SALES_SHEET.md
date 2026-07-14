# Institutional++ — 12 SKU Tech Spec Sales Sheet

**Audience:** Procurement, platform engineering, model risk, auditors  
**Scope:** What each SKU does, technical posture, maturity — **no pricing**  
**Proof baseline:** 246+ smoke tests · rigorous **12/12** · offline `verify-bundle` on every SKU  
**Date:** July 2026

> **Diligence pack:** [INST_PLUS_DILIGENCE_PACK.md](INST_PLUS_DILIGENCE_PACK.md)  
> **Per-SKU deep specs:** `docs/*_SALES_TECH_SPEC.md` · **Buyer one-pagers:** `docs/*_BUYER.md`

---

## How to read maturity %

| % band | Meaning |
|--------|---------|
| **90–95%** | Industry Gold — F1–F9, rigorous E2E, demo, buyer + sales spec, single-instance VPC ✅ |
| **80–89%** | Proof spine complete; buyer-specific integration or HTTP/scale hardening remains |
| **GTM ~15%** | Pre-revenue — no paying tenants; product proof ≠ commercial traction |

**Layers (all SKUs):**

| Layer | What it measures |
|-------|------------------|
| **Inst** | Genesis chain, F1–F9, `export` + offline `verify-bundle`, rigorous CI section |
| **Prod** | Single-tenant air-gap VPC — SQLite + WAL, HTTP `/health` + `/ready` where served |
| **Comm** | Buyer doc + sales tech spec + &lt;60s demo script |
| **Scale** | Redis / Postgres multi-instance profile (optional SOW, not license blocker) |

---

## Portfolio at a glance

| # | Product | SKU | What it does (one line) | Product % | Inst | Prod | Comm |
|---|---------|-----|-------------------------|:---------:|:----:|:----:|:----:|
| 1 | Compliance Logger | `compliance-log` | Tamper-proof regulated decision audit — offline verify | **90%** | ✅ | ✅ | ✅ |
| 2 | Proxy-Risk | `proxy-risk` | Outbound API firewall — rate limit, kill, genesis audit | **90%** | ✅ | ✅ | ✅ |
| 3 | Alt-Data | `altdata` | Alt-data feed with coverage SLA + fail-closed poll proof | **82%** | ✅ | ✅ | ✅ |
| 4 | AI Kit | `ai-kit` | Agent guardrails — checkpoints, rate limits, trace ledger | **82%** | ✅ | ✅ | ✅ |
| 5 | Webhook Mesh | `webhook-mesh` | Inbound webhook idempotency — WAL before ack | **90%** | ✅ | ✅ | ✅ |
| 6 | Ad Guard | `ad-guard` | Marketing API spend kill at boundary | **82%** | ✅ | ✅ | ✅ |
| 7 | Health Telemetry | `health-telemetry` | Device batch tamper evidence (not FDA) | **90%** | ✅ | ✅ | ✅ |
| 8 | ModelGovernor | `model-governor` | ML model lifecycle governance ledger | **90%** | ✅ | ✅ | ✅ |
| 9 | Drift Gate | `drift-gate` | PSI/KS drift enforce inline on feature vectors | **95%** | ✅ | ✅ | ✅ |
| 10 | Webhook Replay | `webhook-replay` | Byte-identical webhook capture + air-gapped replay | **90%** | ✅ | ✅ | ✅ |
| 11 | Spend Guard | `spend-guard` | Reserve → settle → drift lockout API spend wallet | **90%** | ✅ | ✅ | ✅ |
| 12 | Agent Ledger | `agent-ledger` | Pre-execution agent tool authorization + audit | **82%** | ✅ | ✅ | ✅ |

**Portfolio product maturity (weighted):** ~**88%** — all 12 Industry Gold on proof spine; GTM pre-revenue across board.

**Shared spine (`inst_spine`):** genesis WAL, Lamport clocks, F1–F9, deterministic export — licensed with every SKU.

---

## 1 — Compliance Logger

| Field | Detail |
|-------|--------|
| **SKU** | `compliance-log` |
| **Maturity** | **90%** product · GTM ~15% |
| **One job** | Record regulated decisions (approve / deny / escalate) with snapshot + outcome on a genesis hash chain; auditor verifies offline via `verify-bundle`. |
| **Ingress** | CLI `ingest`, HTTP `:8785`, Proof Console |
| **Storage** | `compliance.sqlite` — AppendOnlyLedger + WAL |
| **Gates** | F1–F9; mTLS ingest (rigorous); epoch roots in export |
| **Demo** | `./scripts/demo_compliance_logger.sh` |
| **Non-goals** | GRC workflow (ServiceNow), e-discovery UI, SIEM replacement |
| **Remaining to 100%** | Signed export policy automation; SOC2 evidence pack signing workflow |

**Deep spec:** [COMPLIANCE_LOGGER_SALES_TECH_SPEC.md](COMPLIANCE_LOGGER_SALES_TECH_SPEC.md)

---

## 2 — Proxy-Risk

| Field | Detail |
|-------|--------|
| **SKU** | `proxy-risk` |
| **Maturity** | **90%** product · GTM ~15% |
| **One job** | Outbound API firewall — circuit → schema → rate limit → idempotency → Z-score → shadow or live forward; every gate outcome genesis-logged. |
| **Ingress** | `ProxyRiskGateway.evaluate`, HTTP `:8786`, middleware hook |
| **Modes** | Shadow (no upstream); Live (WAL before upstream; 4xx/5xx → REJECT) |
| **Scale** | `INST_REDIS_URL` — multi-instance token bucket + idempotency |
| **Latency** | p99 &lt; 10ms shadow (industry gold bench) |
| **Integrations** | Optional `PROXY_DRIFT_BASELINE` → Drift Gate (#9) |
| **Demo** | `./scripts/demo_proxy_risk.sh` |
| **Non-goals** | Sub-5ms RTB; inbound webhooks (#5) |
| **Remaining to 100%** | Redis soak in default rigorous path; live auth hardening |

**Deep spec:** [PROXY_RISK_SALES_TECH_SPEC.md](PROXY_RISK_SALES_TECH_SPEC.md)

---

## 3 — Alt-Data

| Field | Detail |
|-------|--------|
| **SKU** | `altdata` |
| **Maturity** | **82%** product · GTM ~15% |
| **One job** | One clean feed with ≥85% field coverage — 4-rung fetch ladder, F7 fail-closed, tamper-evident poll log per cycle. |
| **Ingress** | `poll_once` — stub ctx or `--url` live fetch |
| **Ladder** | primary → mirror → HTML scrape → structural rescue |
| **Storage** | `altdata.sqlite` |
| **Demo** | `./scripts/demo_altdata.sh` |
| **Non-goals** | Full ETL (Fivetran); exchange tick latency |
| **Remaining to 100%** | Buyer feed registry + per-feed CI; live URL auth patterns |

**Deep spec:** [ALTDATA_SALES_TECH_SPEC.md](ALTDATA_SALES_TECH_SPEC.md)

---

## 4 — AI Kit

| Field | Detail |
|-------|--------|
| **SKU** | `ai-kit` |
| **Maturity** | **82%** product · GTM ~15% |
| **One job** | Production agent guardrails — rate limits, Lamport checkpoints, structured output validation, tamper-evident trace ledger (buyer supplies `step_fn`). |
| **Ingress** | `AgentLoop.run_steps` — CLI only |
| **Storage** | `ai_kit_trace.sqlite` |
| **Demo** | `./scripts/demo_ai_kit.sh` |
| **Non-goals** | Hosted LLM; vector DB; LangGraph UI |
| **Remaining to 100%** | Live `step_fn` contract tests; optional OTEL export |

**Deep spec:** [AI_KIT_SALES_TECH_SPEC.md](AI_KIT_SALES_TECH_SPEC.md)

---

## 5 — Webhook Mesh

| Field | Detail |
|-------|--------|
| **SKU** | `webhook-mesh` |
| **Maturity** | **90%** product · GTM ~15% |
| **One job** | Inbound webhooks — HMAC verify → Redis idempotency → WAL fsync → HTTP 200 → async forward; never double-process billing events. |
| **Ingress path** | HMAC → SETNX CAS → WAL → 200 → Redis Stream |
| **Routes** | Stripe, Shopify, generic HMAC |
| **Storage** | `webhook_mesh.sqlite` |
| **Capture** | `WEBHOOK_REPLAY_CAPTURE_DIR` → #10 `.wrcap` |
| **Demo** | `./scripts/demo_webhook_mesh.sh` |
| **Non-goals** | Full event bus (Kafka); Stripe Connect UI |
| **Remaining to 100%** | Stream consumer-group chaos matrix; mTLS ingress default |

**Deep spec:** [WEBHOOK_MESH_SALES_TECH_SPEC.md](WEBHOOK_MESH_SALES_TECH_SPEC.md)

---

## 6 — Ad Guard

| Field | Detail |
|-------|--------|
| **SKU** | `ad-guard` |
| **Maturity** | **82%** product · GTM ~15% |
| **One job** | Marketing API spend kill — Google/Meta parsers, per-campaign bucket, Z-score velocity kill, genesis audit before spend. |
| **Ingress** | `AdGuardGateway.evaluate`, HTTP `:8788` |
| **Stack** | NeMo/Bedrock (safety) → **Ad Guard** (spend) → DSP + DV/IAS (placement) |
| **Demo** | `./scripts/demo_ad_guard.sh` |
| **Non-goals** | RTB sub-5ms; DoubleVerify pre-bid |
| **Remaining to 100%** | Upstream timeout matrix; Redis profile in default CI |

**Deep spec:** [AD_GUARD_SALES_TECH_SPEC.md](AD_GUARD_SALES_TECH_SPEC.md)

---

## 7 — Health Telemetry

| Field | Detail |
|-------|--------|
| **SKU** | `health-telemetry` |
| **Maturity** | **90%** product · GTM ~15% |
| **One job** | Device batch tamper evidence — per-device `seq` gate, WAL-before-ack HTTP ingress, PHI-safe observation-lane export. **Audit spine, not FDA cert.** |
| **Ingress** | CLI `ingest_batch`; HTTP `:8793` |
| **Storage** | `health.sqlite` |
| **Diligence** | [HEALTH_TELEMETRY_HIPAA_PACK.md](HEALTH_TELEMETRY_HIPAA_PACK.md) template |
| **Demo** | `./scripts/demo_health_telemetry.sh` |
| **Non-goals** | FDA/UKCA; EMR/FHIR P1; clinical alerting UI |
| **Remaining to 100%** | Device cert auth; signed BAA workflow |

**Deep spec:** [HEALTH_TELEMETRY_SALES_TECH_SPEC.md](HEALTH_TELEMETRY_SALES_TECH_SPEC.md)

---

## 8 — ModelGovernor

| Field | Detail |
|-------|--------|
| **SKU** | `model-governor` |
| **Maturity** | **90%** product · GTM ~15% |
| **One job** | ML model governance events (register, approve, deploy, retire, drift alert) with model snapshot + `artifact_hash` on genesis chain; offline verify. |
| **Ingress** | CLI `record`; lifecycle FSM fail-closed |
| **Storage** | `model_governor.sqlite` |
| **Integrations** | Deploy-time Drift Gate hook (`lifecycle.py`) |
| **Demo** | `./scripts/demo_model_governor.sh` |
| **Walkthrough** | `make demo-gold` — spend-plane story (uses #11, not a separate SKU) |
| **Non-goals** | Full MLOps platform (MLflow UI); experiment hosting |
| **Remaining to 100%** | Artifact signing in rigorous; deploy gate always-on in CI |

**Deep spec:** [MODEL_GOVERNOR_SALES_TECH_SPEC.md](MODEL_GOVERNOR_SALES_TECH_SPEC.md)

---

## 9 — Drift Gate

| Field | Detail |
|-------|--------|
| **SKU** | `drift-gate` |
| **Maturity** | **95%** product · GTM ~15% |
| **One job** | PSI + KS on live feature vectors — shadow burn-in then inline enforce (reject/kill) with genesis audit per evaluation. |
| **Ingress** | `evaluate_model_features` integrate hook |
| **State** | File or Redis rolling windows |
| **Integrations** | `PROXY_DRIFT_BASELINE` on Proxy-Risk (#2); ModelGovernor deploy gate (#8) |
| **Demo** | `./scripts/demo_drift_gate.sh` |
| **Non-goals** | Full MRM dashboard (Fiddler); fairness certification |
| **Remaining to 100%** | PSI/KS golden-file regression suite in default CI |

**Deep spec:** [DRIFT_GATE_SALES_TECH_SPEC.md](DRIFT_GATE_SALES_TECH_SPEC.md)

---

## 10 — Webhook Replay

| Field | Detail |
|-------|--------|
| **SKU** | `webhook-replay` |
| **Maturity** | **90%** product · GTM ~15% |
| **One job** | Capture raw webhook bytes (`.wrcap`), replay air-gapped, prove idempotent outcomes + tamper detection on genesis chain. |
| **Format** | `.wrcap` — mmap-readable, `payload_sha256` manifest |
| **Integrations** | Auto-capture from Webhook Mesh (#5) |
| **Demo** | `./scripts/demo_webhook_replay.sh` |
| **Non-goals** | Hookdeck/Svix delivery SaaS |
| **Remaining to 100%** | WRCAP corruption fuzz property tests |

**Deep spec:** [WEBHOOK_REPLAY_SALES_TECH_SPEC.md](WEBHOOK_REPLAY_SALES_TECH_SPEC.md)

---

## 11 — Spend Guard

| Field | Detail |
|-------|--------|
| **SKU** | `spend-guard` |
| **Maturity** | **90%** product · GTM ~15% |
| **One job** | Reserve estimated cost before upstream dispatch → settle actual → drift lockout freezes wallet; genesis spend events. |
| **Wallet** | SQLite IMMEDIATE default; Postgres profile optional |
| **Gateway** | OpenAI-compat `/v1/chat/completions` on `:8789` |
| **Semantics** | Reserve → settle → `DRIFT_THRESHOLD_EXCEEDED` lockout |
| **Demo** | `./scripts/demo_spend_guard.sh` · `make demo-gold` (11-step walkthrough) |
| **Non-goals** | LiteLLM routing catalog; multi-currency treasury |
| **Remaining to 100%** | Postgres wallet in default rigorous CI; API key on gateway surface |

**Deep spec:** [SPEND_GUARD_SALES_TECH_SPEC.md](SPEND_GUARD_SALES_TECH_SPEC.md)

---

## 12 — Agent Ledger

| Field | Detail |
|-------|--------|
| **SKU** | `agent-ledger` |
| **Maturity** | **82%** product · GTM ~15% |
| **One job** | Fail-closed runtime governance for agent tool calls — authorize before invoke, deny/escalate, human attestation on critical tools. |
| **Flow** | `authorize_tool_call` → execute (buyer runtime) → `complete_tool_call` |
| **Storage** | `agent_ledger.sqlite` · HTTP `:8792` |
| **Integrations** | AI Kit pipeline hook; LangChain hook documented |
| **Demo** | `./scripts/demo_agent_ledger.sh` |
| **Non-goals** | Full agent framework; LLM spend (#11) |
| **Remaining to 100%** | mTLS / API key on `/v1/authorize`; permit TTL sweep in CI |

**Deep spec:** [AGENT_LEDGER_SALES_TECH_SPEC.md](AGENT_LEDGER_SALES_TECH_SPEC.md)

---

## Shared proof commands

```bash
pip install -e ".[dev,instpp]"
make plug                                    # demo-all 12/12 + offline verify
./scripts/instpp_smoke_test.sh               # 246+ tests
./scripts/instpp_rigorous_test.sh            # 12/12 E2E → docs/test_logs/
make buyer-pack                              # PORTFOLIO_MANIFEST.json
```

Proof Console (guided ingest all 12): `make workflow-serve` → `:8790`

---

## Logical bundles (not separate SKUs)

| Bundle | SKUs | Job |
|--------|------|-----|
| Finance Governor | #11 + #9 (+ #2) | LLM/API spend + drift + outbound firewall |
| Insurance Governor | #8 + #9 + #1 | Model lifecycle + drift + decision audit |
| Agent stack | #12 + #4 + #11 | Tool auth + trace + spend |
| Billing integrity | #5 + #10 | Ingress idempotency + forensic replay |
| Full spine | All 12 | One `PORTFOLIO_MANIFEST.json` |

---

## Related documents

| Doc | Purpose |
|-----|---------|
| [PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md](PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md) | Full competitive positioning per SKU |
| [PORTFOLIO_EVIDENCE_SHEET.md](PORTFOLIO_EVIDENCE_SHEET.md) | CI artifacts and test index |
| [INST_PLUS_PRODUCTION_ARCHITECTURE.md](INST_PLUS_PRODUCTION_ARCHITECTURE.md) | Per-SKU execution map |
| [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) | Nine Industry Gold dimensions |
| [FORENSIC_HARDENING_AUDIT.md](FORENSIC_HARDENING_AUDIT.md) | Per-SKU forensic grades → 10 |
