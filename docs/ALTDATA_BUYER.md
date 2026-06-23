# Alt-Data Extractor — Buyer Sheet

**One job:** One clean telemetry feed with ≥85% field coverage, structural fallback when primary fetchers break, and cryptographic proof per poll cycle.

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| Quant / alt-data teams | Silent gaps when APIs change | Coverage ladder + F7 gate + `CoverageError` fail-closed |
| Ops / data engineering | ETL logs are not audit evidence | Genesis ledger per poll + offline `verify-bundle` |
| Compliance-adjacent feeds | “Prove what the feed contained on date X” | Deterministic export bundle |

**Price band:** £500–£2,000/mo per feed (design partner for live URL targets).

---

## Tech edge (proof)

| Gate | Evidence |
|------|----------|
| F7 | Source field coverage % on each snapshot |
| Ladder | primary → mirror → HTML scrape → structural rescue |
| F3–F4 | Hash chain + Lamport monotonicity per poll |
| F9 | Identical ledger → identical bundle SHA256 |

**Auditor dry-run:**
```bash
altdata poll --feed demo_feed --ctx '{"demo_price":42.5,"demo_seats":180}'
altdata export --database ./altdata.sqlite --tarball ./altdata_bundle.tar
altdata verify-bundle --tarball ./altdata_bundle.tar
```

---

## 60-second demo

```bash
./scripts/demo_altdata.sh
```

Live URL fetch (optional):
```bash
altdata poll --url https://httpbin.org/json --feed live_feed --database ./live.sqlite
```

---

## Non-goals

- Not a full ETL platform (Airflow, Fivetran)
- Not real-time tick ingestion at exchange latency
- Not bundled with HIBS sports products

---

## CLI

| Command | Purpose |
|---------|---------|
| `poll` | Run one poll cycle (stub ctx or `--url`) |
| `check` | F1–F9 + coverage floor |
| `export` | Deterministic audit bundle |
| `verify-bundle` | Offline auditor replay |

See `src/altdata/README.md` for architecture.
