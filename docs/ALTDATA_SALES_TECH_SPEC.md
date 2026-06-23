# Alt-Data Extractor — Sales & Technical Specification

**Product:** Alt-Data Extractor (#3)  
**SKU:** `altdata`  
**Version:** Gold standard (production feeds, F7 coverage gate, offline verify-bundle)  
**Audience:** Quant research, data engineering, compliance-adjacent feed owners, procurement

---

## Executive summary

**One job:** Deliver **one clean telemetry feed** with ≥85% field coverage, structural fallback when primary fetchers break, and **cryptographic proof per poll cycle**.

**One-line pitch:** *Know what your feed contained on date X — and fail closed when coverage drops.*

| | |
|---|---|
| **Price band** | £500–£2,000/mo per feed (design partner for live URL targets) |
| **Deploy** | Air-gapped VPC / on-prem — SQLite + WAL |
| **Proof** | Genesis ledger per poll + F7 coverage gate + `verify-bundle` |
| **Demo** | 60 seconds CLI · production FX feed optional |

---

## Problem → solution

| Buyer pain | Industry default | Alt-Data |
|------------|------------------|----------|
| Silent gaps when APIs change | Dashboard alert next day | **Coverage ladder + F7 fail-closed** |
| ETL logs are not audit evidence | Airflow logs (mutable) | **Genesis ledger per poll + export** |
| “Prove feed on date X” | CSV export (editable) | **Deterministic tar + SHA256 sidecar** |
| Primary fetcher down | Manual failover | **4-rung ladder: primary → mirror → scrape → structural rescue** |
| Reproducibility disputes | Non-deterministic exports | **F9 — identical ledger → identical bundle SHA256** |

---

## Ideal buyer

| Segment | Use case | Why us |
|---------|----------|--------|
| **Quant / alt-data** | FX, seats, pricing telemetry | Coverage as institutional gate, not dashboard |
| **Data engineering** | Replace brittle scrapers | Structural rescue rung + typed `CoverageError` |
| **Compliance-adjacent feeds** | Prove feed integrity for disputes | Offline `verify-bundle` |

**Win when:** buyer needs **coverage SLA + tamper-evident poll log**.  
**Lose when:** buyer needs full ETL catalog (Fivetran, Airflow enterprise) or exchange tick latency.

---

## Competitive positioning

| Capability | Generic scrapers | ETL SaaS | **Alt-Data** |
|------------|------------------|----------|--------------|
| Coverage as gate | Ad-hoc | Dashboard | **F7 institutional check** |
| Structural rescue | Rare | Manual | **Rung-4 regex/HTML** |
| Tamper-evident poll log | No | No | **Genesis ledger per poll** |
| Offline verify | No | No | **`verify-bundle`** |
| Fail-closed low coverage | No | Alert only | **`CoverageError` on poll** |

---

## Architecture

```
poll → field ladder (primary → mirror → scrape → structural rescue)
     → coverage % (F7)
     → ledger append (hash chain + Lamport)
     → F1–F9 check → export → verify-bundle
```

### Production feeds

```bash
altdata list-feeds
altdata poll --production-feed fx_gbp_cross   # Frankfurter FX API
altdata poll --url https://... --feed custom  # buyer URL override
```

Stub ctx available offline: `SKIP_LIVE=1` or demo script.

---

## CLI reference

```bash
pip install -e ".[dev,instpp]"
```

| Command | Purpose |
|---------|---------|
| `altdata poll --feed NAME [--ctx JSON] [--url URL] [--production-feed ID]` | One poll cycle |
| `altdata list-feeds` | Registered production feed registry |
| `altdata check [--database PATH]` | F1–F9 + coverage floor |
| `altdata export [--database PATH] [--tarball PATH]` | Deterministic audit bundle |
| `altdata verify-bundle --tarball PATH` | Offline auditor replay |

---

## Proof & diligence

```bash
./scripts/demo_altdata.sh
./scripts/instpp_rigorous_test.sh
altdata verify-bundle --tarball ./altdata_bundle.tar
```

| Artifact | Path |
|----------|------|
| Rigorous test log | `docs/test_logs/instpp_rigorous_latest.log` |
| Buyer one-pager | `docs/ALTDATA_BUYER.md` |
| Architecture | `src/altdata/README.md` |

---

## Non-goals (say no in RFPs)

- Not a full ETL platform (Airflow, Fivetran, dbt Cloud)
- Not real-time tick ingestion at exchange latency
- Not bundled with HIBS sports products
- Not a data catalog or lineage UI

---

## Pricing & packaging

| Tier | Band | Includes |
|------|------|----------|
| **Feed license** | £500–£2,000/mo | CLI + spine + one feed config + export |
| **Design partner** | £2k–£5k SOW | Live URL mapping, ladder tuning, coverage floor |
| **Additional feed** | +50% per feed | Same spine, separate ledger |
| **Maintenance** | 15–20% ARR | Security patches, feed registry updates |

---

## RFP quick answers

| Question | Answer |
|----------|--------|
| Prove feed content on date X? | **Yes** — poll ledger + export |
| Fail-closed on low coverage? | **Yes** — F7 + `CoverageError` |
| Offline third-party verification? | **Yes** — `verify-bundle` |
| Air-gapped deploy? | **Yes** |
| Full ETL orchestration? | **No** |
| Sub-millisecond tick data? | **No** |

---

## Related documents

- `docs/ALTDATA_BUYER.md` — one-page buyer sheet  
- `docs/PORTFOLIO_SALES_SHEET.md` — portfolio pricing matrix  
- `docs/BUYER_EVIDENCE_PACK.md` — procurement dry-run
