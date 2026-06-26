# Institutional Standard — Full Portfolio (12 SKUs)

**Purpose:** Industry Gold bar — every product meets nine dimensions on `inst_spine`.  
**Internal spine:** `inst_spine` (genesis WAL, F-gates, deterministic export).

See also: `docs/INST_PLUS_GOLD_STANDARD.md` (full matrix) · `docs/PORTFOLIO_FULL_TECH_SALES_12.md` (SKU index)

---

## Nine dimensions

| # | Dimension | Requirement |
|---|-----------|-------------|
| 1 | **Correctness** | Fail-closed; all gate outcomes logged |
| 2 | **Failure handling** | `InstError` + `run_cli()` JSON envelope |
| 3 | **Proof** | `export` + offline `verify-bundle` |
| 4 | **Demoability** | `scripts/demo_<product>.sh` in &lt;60s |
| 5 | **Diligence** | README + buyer doc + sales spec |
| 6 | **Legibility** | One job + explicit non-goals |
| 7 | **Chaos** | WAL / wallet / capture failure paths |
| 8 | **Latency** | Hot path p99 documented (&lt;10ms proxy shadow) |
| 9 | **Rigorous E2E** | `instpp_rigorous_test.sh` section per SKU |

## Product matrix — Industry Gold

| # | Product | Grade | Demo | Buyer doc |
|---|---------|-------|------|-----------|
| 1 | Compliance Logger | Industry | `demo_compliance_logger.sh` | `COMPLIANCE_LOGGER_BUYER.md` |
| 2 | Proxy-Risk Gateway | Industry | `demo_proxy_risk.sh` | `PROXY_RISK_BUYER.md` |
| 3 | Alt-Data Extractor | Industry | `demo_altdata.sh` | `ALTDATA_BUYER.md` |
| 4 | AI Kit | Industry | `demo_ai_kit.sh` | `AI_KIT_BUYER.md` |
| 5 | Webhook Mesh | Industry | `demo_webhook_mesh.sh` | `WEBHOOK_MESH_BUYER.md` |
| 6 | Ad Guard | Industry | `demo_ad_guard.sh` | `AD_GUARD_BUYER.md` |
| 7 | Health Telemetry | Industry | `demo_health_telemetry.sh` | `HEALTH_TELEMETRY_BUYER.md` |
| 8 | ModelGovernor 8a | Industry | `demo_model_governor.sh` | `MODEL_GOVERNOR_BUYER.md` |
| 9 | Drift Gate | Industry | `demo_drift_gate.sh` | `DRIFT_GATE_BUYER.md` |
| 10 | Webhook Replay | Industry | `demo_webhook_replay.sh` | `WEBHOOK_REPLAY_BUYER.md` |
| 11 | Spend Guard (8b) | Industry | `demo_spend_guard.sh` · `make demo-gold` | `SPEND_GUARD_BUYER.md` |
| 12 | Agent Ledger | Industry | `demo_agent_ledger.sh` | `AGENT_LEDGER_BUYER.md` |

## Proof commands

```bash
pip install -e ".[dev,instpp]"
make plug                                 # demo-all + verify 12/12
./scripts/instpp_smoke_test.sh            # 157+ tests
./scripts/instpp_rigorous_test.sh         # 12/12 products + chaos + demo-gold
./scripts/chaos_instpp.sh
```

### macOS setup (required for gold-standard test pass)

Default macOS open-file limit (`ulimit -n` ≈ 256) exhausts during the SQLite-heavy suite. The smoke/rigorous scripts auto-raise the limit and prune stale pytest temp dirs.

**Recommended Python:** 3.10–3.13 (3.14 is experimental).

```bash
cd /path/to/hibs-bet-racing
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev,instpp]"
./scripts/instpp_smoke_test.sh
```

**Deep dive:** `docs/INST_PLUS_DEEP_DIVE_ALL_7.md` (legacy 8-product doc)  
**12-SKU index:** `docs/PORTFOLIO_FULL_TECH_SALES_12.md`  
**SOC 2 / VPC diligence:** `docs/SOC2_VPC_DILIGENCE_PACK.md`  
**Evidence pack:** `docs/BUYER_EVIDENCE_PACK.md`
