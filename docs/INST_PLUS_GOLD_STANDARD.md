# Institutional Gold Standard — Full Portfolio (11 SKUs)

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

**ModelGovernor 8b compose demo** (`make demo-gold`): documented north star — Postgres stack not in rigorous CI; **Spend Guard** is the shipped CLI for spend-plane proof.

---

## Tech edges (portfolio-wide)

| Edge | SKUs |
|------|------|
| Offline `verify-bundle` (auditor never calls vendor) | All 11 |
| Genesis anti-wipe + Lamport clocks | All 11 |
| WAL-before-side-effect | #5 Webhook Mesh, ingress capture |
| Reserve → settle → drift lockout | #11 Spend Guard |
| PSI/KS enforce at proxy | #9 Drift Gate + #2 Proxy-Risk |
| Byte-identical webhook replay | #10 Webhook Replay |
| Shadow → live burn-in | #2 Proxy-Risk, #9 Drift Gate |

---

## Quick proof commands

```bash
pip install -e ".[dev,instpp]"
./scripts/instpp_smoke_test.sh          # 113+ unit tests
./scripts/instpp_rigorous_test.sh       # 11/11 rigorous E2E → docs/test_logs/
./scripts/chaos_instpp.sh               # chaos + integration drills
./scripts/demo_portfolio_all.sh         # original 8 demos
./scripts/demo_phase2_all.sh            # drift-gate + webhook-replay + spend-guard
```

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
- Batch schema validation; Lamport per batch; HIPAA pack

### #8 ModelGovernor 8a
- Model snapshot contract; governance actions on chain

### #9 Drift Gate
- PSI/KS per feature; shadow/enforce; Redis rolling state

### #10 Webhook Replay
- WRCAP mmap capture; air-gapped replay; tamper diff

### #11 Spend Guard
- Reserve/settle IMMEDIATE; drift lockout; 8b CLI canonical

---

## Related documents

- `docs/BUYER_EVIDENCE_PACK.md` — procurement 15-minute script
- `docs/PORTFOLIO_TECH_SALES_SHEET.md` — license economics
- `docs/SOC2_VPC_DILIGENCE_PACK.md` — VPC diligence
- `docs/INSTITUTIONAL_STANDARD.md` — portfolio overview
