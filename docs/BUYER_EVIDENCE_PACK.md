# Buyer Evidence Pack — Procurement & Auditor Dry-Run

**Purpose:** Hand this to procurement, InfoSec, or an external auditor — run proof **without a vendor call**.  
**Scope:** All 8 institutional products on shared `inst_spine`  
**Last rigorous E2E:** 8/8 PASSED (see `docs/test_logs/instpp_rigorous_latest_summary.json`)

---

## What you are buying (evidence, not promises)

| Evidence type | What it proves |
|---------------|----------------|
| **91 automated tests** | Fail-closed gates, hash chain, export determinism |
| **Rigorous E2E 8/8** | Each product: ingest → check → export → verify-bundle |
| **Offline verify-bundle** | Auditor replays tarball without live DB or vendor API |
| **Deterministic F9** | Identical ledger → identical bundle SHA256 |
| **Typed errors** | No silent drops — `InstError` hierarchy + JSON CLI envelope |
| **Demo scripts** | Reproducible &lt;60s proof per SKU |

---

## 15-minute diligence script

```bash
git clone <repo> && cd <repo>
pip install -e ".[dev,instpp]"

# Full test suite
./scripts/instpp_smoke_test.sh

# Per-product E2E (logged)
./scripts/instpp_rigorous_test.sh
cat docs/test_logs/instpp_rigorous_latest_summary.json

# All demos
./scripts/demo_instpp.sh
```

**Expected:** smoke tests green; rigorous summary `"status": "PASSED"`; demo bundles verify offline.

---

## Per-product auditor commands

| # | Product | Verify offline |
|---|---------|----------------|
| 1 | Compliance Logger | `compliance-log verify-bundle --tarball ./compliance_bundle.tar` |
| 2 | Proxy-Risk | `proxy-risk verify-bundle --tarball ./proxy_bundle.tar` |
| 3 | Alt-Data | `altdata verify-bundle --tarball ./altdata_bundle.tar` |
| 4 | AI Kit | `ai-kit verify-bundle --tarball ./ai_kit_bundle.tar` |
| 5 | Webhook Mesh | `webhook-mesh verify-bundle --tarball ./webhook_mesh_bundle.tar` |
| 6 | Ad Guard | `ad-guard verify-bundle --tarball ./ad_guard_bundle.tar` |
| 7 | Health Telemetry | `health-telemetry verify-bundle --tarball ./health_bundle.tar` |
| 8 | ModelGovernor | `model-governor verify-bundle --tarball ./model_governor_bundle.tar` |

Demo scripts write bundles to predictable paths — run `./scripts/demo_<product>.sh` first.

---

## Export bundle contents (every SKU)

| File | Contents |
|------|----------|
| `MANIFEST.json` | Product id, entry count, validation summary |
| `ledger_entries.json` | Full hash chain |
| `institutional_check.json` | F1–F9 + chain gates |
| `genesis_anchor.json` | Offsite-verifiable genesis |
| `wal_full.json` | Crash-safe WAL replay |
| `audit_bundle.tar` | Deterministic bytes |
| `audit_bundle.tar.sha256.json` | Cryptographic seal |

---

## Institutional gates (F1–F9) — shared bar

| Gate | What it checks |
|------|----------------|
| ledger_chain | Sequential hash integrity |
| genesis_block | Installation origin matches anchor |
| lamport_order | Logical clock strictly increasing |
| F1–F2 | Snapshot completeness + manifest linkage |
| F3–F4 | Hash chain + Lamport monotonicity |
| F5 | Config hash stable vs genesis anchor |
| F6 | Entry count reconciliation |
| F7 | Source field coverage % |
| F8 | Retention policy compliance |
| F9 | Identical ledger → identical bundle SHA256 |

Full matrix: `docs/INSTITUTIONAL_STANDARD.md`

---

## Security & compliance artifacts

| Document | Applies to |
|----------|------------|
| [SOC2_VPC_DILIGENCE_PACK.md](SOC2_VPC_DILIGENCE_PACK.md) | All 8 — VPC deploy, CC mapping |
| [HEALTH_TELEMETRY_HIPAA_PACK.md](HEALTH_TELEMETRY_HIPAA_PACK.md) | #7 — BAA diligence template |
| [HEALTH_TELEMETRY_HOSPITAL_PILOT.md](HEALTH_TELEMETRY_HOSPITAL_PILOT.md) | #7 — ward pilot playbook |

**Procurement line:** Deploy in buyer VPC; SOC 2 scope is buyer-operated; vendor scope is provable correctness of audit spine.

---

## Test log artifacts

| Artifact | Path |
|----------|------|
| Latest summary JSON | `docs/test_logs/instpp_rigorous_latest_summary.json` |
| Latest full log | `docs/test_logs/instpp_rigorous_latest.log` |
| Historical logs | `docs/test_logs/instpp_rigorous_*.log` |

---

## Sales collateral index

| Doc | Use when |
|-----|----------|
| [PORTFOLIO_SALES_SHEET.md](PORTFOLIO_SALES_SHEET.md) | First meeting — all 8 SKUs + pricing |
| `docs/*_BUYER.md` | 60-second skim per product |
| `docs/*_SALES_TECH_SPEC.md` | RFP / security questionnaire depth |
| [INST_PLUS_DEEP_DIVE_ALL_7.md](INST_PLUS_DEEP_DIVE_ALL_7.md) | Technical architecture review |

---

## Honest limits (say yes/no in RFPs)

| Ask | Answer |
|-----|--------|
| Offline verify without vendor | **Yes** |
| Air-gap deploy | **Yes** |
| SOC 2 Type II SaaS cert | **No** — VPC pack instead |
| GRC workflow UI | **No** |
| Sub-5ms RTB | **No** |
| FDA / DTAC device cert | **No** (#7 is audit spine only) |
| Hosted LLM | **No** (#4 — buyer supplies model) |
