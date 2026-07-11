# Institutional++ — Diligence Pack (self-contained)

**Everything for technical evaluation, sales positioning, and market comparison lives in this pack.**  
**No Inst++ pricing** — procurement terms are offline, not in repo docs.  
**Comparable market pricing** is included only in the platform compare doc (third-party vendors).  
**Date:** July 2026

---

## Read in this order

| # | Document | What it covers |
|---|----------|----------------|
| 1 | [PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md](PORTFOLIO_FULL_TECH_SALES_NO_PRICES.md) | **Full tech & sales** — 12 SKUs, buyer segments, problem→solution, competitive positioning, proof commands, completion matrix |
| 2 | [PORTFOLIO_EVIDENCE_SHEET.md](PORTFOLIO_EVIDENCE_SHEET.md) | **Factual evidence** — CI artifacts, rigorous sections, per-SKU test files, docker-extended logs |
| 3 | [INST_PLUS_PLATFORM_COMPARE.md](INST_PLUS_PLATFORM_COMPARE.md) | **Market deep dive** — capability matrix vs Hookdeck, Svix, Kong, ServiceNow GRC, Langfuse, LiteLLM, Fiddler, etc. + **2025–2026 public pricing bands** |
| 4 | [INST_PLUS_PRODUCTION_ARCHITECTURE.md](INST_PLUS_PRODUCTION_ARCHITECTURE.md) | **Production map** — spine architecture, per-SKU execution paths, `/ready` criteria, Proof Console ingest |

---

## 15-minute proof run

```bash
pip install -e ".[dev,instpp]"
make plug
./scripts/instpp_smoke_test.sh
cat docs/test_logs/instpp_rigorous_latest_summary.json
make demo-gold                    # Spend Guard walkthrough
```

With Docker:

```bash
make docker-extended
cat docs/test_logs/instpp_docker_extended_latest_summary.json
```

---

## Per-SKU depth (in this repo)

| Layer | Path |
|-------|------|
| Buyer one-pagers | `docs/*_BUYER.md` |
| Technical specs | `docs/*_SALES_TECH_SPEC.md` |
| Test logs | [test_logs/README.md](test_logs/README.md) |
| Gold standard bar | [INST_PLUS_GOLD_STANDARD.md](INST_PLUS_GOLD_STANDARD.md) |
| Run guide | [RUN_DEMO.md](RUN_DEMO.md) |

---

## What is intentionally not in this pack

- Inst++ license bands, ARR projections, or valuation framing (see `PORTFOLIO_TECH_SALES_SHEET.md` for priced internal conversations only)  
- Sports / trading / governor consumer apps (out of SKU scope)
