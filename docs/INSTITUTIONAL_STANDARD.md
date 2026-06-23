# Institutional Standard — All 7 Products

**Purpose:** The bar every infrastructure product in this portfolio strives to meet.  
**Internal spine:** `inst_spine` (genesis WAL, F-gates, deterministic export) — not a product name.

See also: `docs/INST_PLUS_GOLD_STANDARD.md` (detailed criteria matrix).

---

## Six dimensions

| Dimension | Requirement |
|-----------|-------------|
| **Correctness** | Fail-closed; all gate outcomes logged |
| **Failure handling** | `InstError` + `run_cli()` JSON envelope |
| **Proof** | `export` + offline `verify-bundle` |
| **Demoability** | `scripts/demo_<product>.sh` in &lt;60s |
| **Diligence** | README + buyer doc per product |
| **Legibility** | One job + explicit non-goals |

## Product matrix

| # | Product | Grade | Demo | Buyer doc |
|---|---------|-------|------|-----------|
| 1 | Compliance Logger | Gold | `demo_compliance_logger.sh` | `COMPLIANCE_LOGGER_BUYER.md` |
| 2 | Proxy-Risk Gateway | Gold | `demo_proxy_risk.sh` | `PROXY_RISK_BUYER.md` |
| 3 | Alt-Data Extractor | Gold | `demo_altdata.sh` | `ALTDATA_BUYER.md` |
| 4 | AI Kit | Gold | `demo_ai_kit.sh` | `AI_KIT_BUYER.md` |
| 5 | Webhook Mesh | Gold | `demo_webhook_mesh.sh` | `WEBHOOK_MESH_BUYER.md` |
| 6 | Ad Guard | Gold | `demo_ad_guard.sh` | `AD_GUARD_BUYER.md` |
| 7 | Health Telemetry | Gold | `demo_health_telemetry.sh` | `HEALTH_TELEMETRY_BUYER.md` |

## Proof commands

```bash
pip install -e ".[dev,instpp]"
./scripts/instpp_smoke_test.sh
./scripts/instpp_rigorous_test.sh    # all 7 products
```

**Deep dive:** `docs/INST_PLUS_DEEP_DIVE_ALL_7.md`  
**SOC 2 / VPC diligence:** `docs/SOC2_VPC_DILIGENCE_PACK.md`
