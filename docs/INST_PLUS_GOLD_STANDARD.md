# Institutional Gold Standard — Full Portfolio (12 SKUs)

**Purpose:** The bar every infrastructure product in this portfolio meets — CLI Gold plus Industry Gold dimensions.

**Internal spine:** `inst_spine` (genesis WAL, F-gates, deterministic export).

---

## Nine dimensions (every product)

| # | Dimension | Requirement | Proof command |
|---|-----------|-------------|---------------|
| 1 | **Correctness** | Fail-closed; all gate outcomes logged | Unit + integration tests |
| 2 | **Failure handling** | `InstError` + `run_cli()` envelope | CLI stderr JSON on error |
| 3 | **Proof** | `export` + offline `verify-bundle` | `*-bundle verify-bundle --tarball …` |
| 4 | **Demoability** | One script, &lt;60s | `scripts/demo_<product>.sh` |
| 5 | **Diligence** | README + buyer doc + sales spec | `docs/*_BUYER.md` + `docs/*_SALES_TECH_SPEC.md` |
| 6 | **Strategic legibility** | One job + explicit non-goals | Buyer doc non-goals section |
| 7 | **Chaos** | WAL / wallet / capture survive failure paths | `scripts/chaos_instpp.sh` + `tests/test_industry_gold.py` |
| 8 | **Latency** | Hot path p99 documented | Proxy p99 &lt;10ms in rigorous + industry gold tests |
| 9 | **Rigorous E2E** | ingest → check → export → verify in CI log | `scripts/instpp_rigorous_test.sh` |

**Industry Gold** = all nine dimensions ✅ for the SKU.

---

## Product readiness matrix — Industry Gold

| # | Product | CLI | verify-bundle | Rigorous E2E | Buyer | Sales spec | Chaos | Integration | Grade |
|---|---------|-----|---------------|--------------|-------|------------|-------|-------------|-------|
| 1 | Compliance Logger | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | spine | **Industry** |
| 2 | Proxy-Risk | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | drift-gate | **Industry** |
| 3 | Alt-Data | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | spine | **Industry** |
| 4 | AI Kit | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | spine | **Industry** |
| 5 | Webhook Mesh | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | webhook-replay | **Industry** |
| 6 | Ad Guard | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | spine | **Industry** |
| 7 | Health Telemetry | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | spine | **Industry** |
| 8 | ModelGovernor 8a | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | drift-gate | **Industry** |
| 9 | Drift Gate | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Proxy-Risk | **Industry** |
| 10 | Webhook Replay | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Webhook Mesh | **Industry** |
| 11 | Spend Guard (8b CLI) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | Proxy-Risk | **Industry** |
| 12 | Agent Ledger | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | AI Kit + spine | **Industry** |

**ModelGovernor 8b compose demo**: design-partner north star — **Spend Guard CLI** + `make demo-gold` is the shipped spend-plane proof.

---

## Tech edges (portfolio-wide)

| Edge | SKUs |
|------|------|
| Offline `verify-bundle` (auditor never calls vendor) | All 12 |
| Genesis anti-wipe + Lamport clocks | All 12 |
| WAL-before-side-effect + Redis Stream delivery | #5 Webhook Mesh |
| Per-device sequence gate + ingress WAL-before-ack | #7 Health Telemetry |
| Authorize → complete attestation (agent tools) | #12 Agent Ledger |
| Reserve → settle → drift lockout + OpenAI-compat gateway | #11 Spend Guard |
| PSI/KS enforce at proxy | #9 Drift Gate + #2 Proxy-Risk |
| Byte-identical webhook replay | #10 Webhook Replay |
| Shadow → live burn-in | #2 Proxy-Risk, #9 Drift Gate |

---

## Quick proof commands

```bash
pip install -e ".[dev,instpp]"
make plug                               # one-shot: demo-all + offline verify 12/12
make demo-ready                         # preflight
make demo-all                           # all 12 demos → data/demo/portfolio/
make verify-portfolio                   # offline verify-bundle → PORTFOLIO_MANIFEST.json
make demo-gold                          # spend-plane sales walkthrough
./scripts/instpp_smoke_test.sh          # 134+ unit tests
./scripts/instpp_rigorous_test.sh       # 12/12 rigorous E2E → docs/test_logs/
./scripts/chaos_instpp.sh               # chaos + integration drills
```

See [RUN_DEMO.md](RUN_DEMO.md) for the full plug/demo/run guide.

---

## Per-product correctness guarantees

### #1 Compliance Logger
- Export aborts on institutional failure
- F7 from real snapshot coverage
- Offline `verify-bundle`

### #2 Proxy-Risk
- Every gate outcome logged
- Live: WAL before upstream; 4xx/5xx → REJECT
- Redis fail-closed
- Optional `PROXY_DRIFT_BASELINE` → drift-gate on hot path

### #3 Alt-Data
- `CoverageError` below floor
- Field ladder + rescue metadata in ledger

### #4 AI Kit
- `RateLimitError` typed (not traceback)
- Lamport checkpoints + trace ledger export

### #5 Webhook Mesh
- HMAC fail → 401
- Idempotency fail-closed on Redis error
- WAL before HTTP 200
- `WEBHOOK_REPLAY_CAPTURE_DIR` → byte capture

### #6 Ad Guard
- All approve/reject/kill logged
- Redis idempotency; live upstream fail-closed

### #7 Health Telemetry
- Packet contract (`ts`, `seq`, profile fields) + F7 coverage at ingest
- Per-device monotonic sequence gate (gap/backward fail-closed)
- HTTP `POST /v1/telemetry/batch` — ingress WAL fsync before ack
- `--observation-lane` export redacts raw packets; summaries + chain retained
- HIPAA pack (template — not signed BAA)

### #8 ModelGovernor 8a
- Model snapshot contract; governance actions on chain

### #9 Drift Gate
- PSI/KS per feature; shadow/enforce; Redis rolling state

### #10 Webhook Replay
- WRCAP mmap capture; air-gapped replay; tamper diff

### #11 Spend Guard
- Reserve/settle IMMEDIATE; drift lockout; OpenAI-compat gateway

### #12 Agent Ledger
- Authorize-before-invoke on agent tool calls
- Risk-tier policy + argument guards fail-closed
- Permit → complete attestation chain
- Offline `verify-bundle`

---

## Related documents

- `docs/BUYER_EVIDENCE_PACK.md` — procurement 15-minute script
- `docs/PORTFOLIO_TECH_SALES_SHEET.md` — license economics
- `docs/SOC2_VPC_DILIGENCE_PACK.md` — VPC diligence
- `docs/INSTITUTIONAL_STANDARD.md` — portfolio overview
