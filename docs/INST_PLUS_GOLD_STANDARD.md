# Inst++ Gold Standard — All 7 Products

**Purpose:** What **Institutional++** grade means for every Inst++ SKU, and how we prove each dimension.

---

## Six dimensions (every product)

| Dimension | Requirement | Proof command |
|-----------|-------------|---------------|
| **Correctness** | Fail-closed; all gate outcomes logged | Unit + integration tests |
| **Failure handling** | `InstError` + `run_cli()` envelope | CLI stderr JSON on error |
| **Proof** | `export` + offline `verify-bundle` | `*-bundle verify-bundle --tarball …` |
| **Demoability** | One script, &lt;60s | `scripts/demo_<product>.sh` |
| **Diligence** | README + buyer/spec doc | `docs/*_BUYER.md` or sales tech spec |
| **Strategic legibility** | One job + explicit non-goals | Deep dive per product |

---

## Product readiness matrix

| # | Product | CLI | verify-bundle | F1–F9 check | run_cli | Demo script | Grade |
|---|---------|-----|---------------|-------------|---------|-------------|-------|
| 1 | Compliance Logger | ✅ | ✅ | ✅ | ✅ | `demo_compliance_logger.sh` | **Gold** |
| 2 | Proxy-Risk | ✅ | ✅ | ✅ | ✅ | `demo_proxy_risk.sh` | **Gold** |
| 3 | Alt-Data | ✅ | ✅ | ✅ | ✅ | `demo_altdata.sh` | **P1+** |
| 4 | AI Kit | ✅ | ✅ | ✅ | ✅ | `demo_ai_kit.sh` | **P1+** |
| 5 | Webhook Mesh | ✅ | ✅ | ✅ | ✅ | `demo_webhook_mesh.sh` | **P1+** |
| 6 | Ad Guard | ✅ | ✅ | ✅ | ✅ | `demo_ad_guard.sh` | **P1+** |
| 7 | Health Telemetry | ✅ | ✅ | ✅ | ✅ | `demo_health_telemetry.sh` | **Scaffold** |

**Rigorous E2E log:** `scripts/instpp_rigorous_test.sh` — products #1–#2 (extend to #5–#6 next).

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

### #3 Alt-Data
- `CoverageError` below floor
- Field ladder + rescue metadata in ledger
- Export aborts on F-gate fail

### #4 AI Kit
- `RateLimitError` typed (not traceback)
- Lamport checkpoints + trace ledger export
- `validate_with_retry` in run path

### #5 Webhook Mesh
- HMAC fail → 401
- Idempotency fail-closed on Redis error
- WAL before HTTP 200; genesis ledger cold path

### #6 Ad Guard
- All approve/reject/kill logged
- Redis idempotency (not process-local only)
- Live upstream fail-closed

### #7 Health Telemetry
- Batch schema validation
- Genesis chain per device batch
- Export + verify-bundle (scaffold)

---

## Quick proof commands

```bash
pip install -e ".[dev,instpp]"
./scripts/instpp_smoke_test.sh
./scripts/demo_instpp.sh                    # #1 + #2
./scripts/demo_altdata.sh                   # #3
./scripts/demo_ai_kit.sh                    # #4
./scripts/demo_webhook_mesh.sh                # #5
./scripts/demo_ad_guard.sh                  # #6
./scripts/demo_health_telemetry.sh          # #7
```

---

## Related

- `docs/INST_PLUS_DEEP_DIVE_ALL_7.md` — full tech edge per product
- `docs/INST_PLUS_PRE_REV_VALUATION.md` — IP valuation
- `docs/INST_PLUS_TEST_AND_DEMO.md` — command playbook
