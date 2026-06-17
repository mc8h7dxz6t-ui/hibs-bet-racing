# Inst++ Portfolio Strategy — HIBS vs New Products

**Purpose:** Laser-focused direction after HIBS harvest — what to sell, what's worth building, and how UK governance maps to Inst++.

---

## Executive verdict

You have **two distinct portfolios** — do not conflate them in pitch or pricing:

| Portfolio | Buyer | Value driver | Realistic exit (code only) | Realistic exit (with traction) |
|-----------|-------|--------------|---------------------------|-------------------------------|
| **HIBS** (football + racing + trading) | Quant syndicates, acquirers | Proven alpha + audit trail | £40k–£70k bundle | £250k–£500k+ **only with ARR** |
| **Inst++** (4 spine products) | B2B infra buyers | Cost-to-replicate + compliance | £45k–£70k ecosystem | £195k–£260k at min promotion |

**Critical valuation truth:** Acquire/Flippa buy **cash flow**, not algorithms. £450k–£700k HIBS targets require ~£100k+ clean annual profit (3.5–4x SDE), not 60 days of clean logs alone.

**60-day family runway goal:** Reframe as **commercialisation runway** (first £2k–£7.5k MRR), not "code appreciation to £450k."

---

## HIBS — keep, harvest, don't over-build

### What you have (proven engineering)

- Football: Dixon–Coles + LightGBM, F1–F9 evidence gates, `prediction_audit.sqlite`
- Racing: Inst++ layer live (WAL, genesis, gates) — 26 tests passing
- Trading Core: staged pipeline Shadow → Paper → Micro → Live

### Monetisation paths (ranked by fit to your skills)

| Path | Model | ARR to hit £300k valuation | Your edge |
|------|-------|------------------------------|-----------|
| **A. B2B JSON data feed** | 5 × £1,500/mo | £90k ARR | Already have HTTP JSON + data room exports |
| **B. Private signal community** | 100 × £99/mo | ~£118k ARR | Place-finder hit rates market well |
| **C. Trading Core boilerplate** | N/A — overlaps Inst++ Proxy-Risk | — | **Don't duplicate** — sell spine not alpha |

### Success probability (honest)

| Outcome | Rough probability |
|---------|-------------------|
| Technical soak (no crashes, clean logs) | **~90%** |
| Model alpha (edge after commission/slippage) | **~40–50%** |
| Commercial monetisation (paying strangers) | **~10–15%** |

**Tilt odds:** Public verification dashboard + pre-sell beta data access **now**, not day 60.

---

## Inst++ — four products (laser-focused)

Built on `src/inst_spine/` — **zero sports imports**. Sell **individually**, not as one bundle.

| # | Product | One job | Code status | Next to 95% |
|---|---------|---------|-------------|-------------|
| 1 | **Compliance Logger** | Tamper-proof decision audit | P1 ingest + genesis | **P2 export (this PR)** |
| 2 | **Proxy-Risk Gateway** | Circuit breaker middleware | P1 shadow async | Upstream forward + p99 bench |
| 3 | **Alt-Data Extractor** | One feed, ≥95% coverage | P1 demo ladder | Wire **one real** non-sports target |
| 4 | **AI Kit** | Rate limits + checkpoints | P1 demo | Pydantic retry E2E |

**Build order (unchanged):** Compliance P2 → Proxy-Risk P2 → Alt-Data one feed → AI Kit P2.

---

## UK Code for Sports Governance — Inst++ mapping

Funded NGBs (Tier 1–3) need what Inst++ already builds — **not betting tips**:

| Code principle | Inst++ product | Evidence |
|----------------|----------------|----------|
| **Standards & Conduct** | Compliance Logger | F1–F9 gates + genesis chain |
| **Policies & Processes** | Compliance Logger | `export_audit.sh` auditor bundle |
| **Communication / Transparency** | Compliance + public verify page | Deterministic tar + SHA256 sidecar |
| **Financial discipline / risk** | Proxy-Risk Gateway | Token bucket + Z-score kill |

**Laser focus for UK sport:** Don't sell "betting platform" to NGBs. Sell **governance-grade audit infrastructure** — the same spine Compliance Logger ships to fintech.

Tier 3 NGBs (£1m+ funding) need DIAP + welfare board roles → your product is **audit trail + risk kill-switch**, not racecards.

---

## Compliance P2 — export pipeline (implemented)

```
[WAL] + [Genesis anchor] + [SQLite index]
         │
         ▼
  validate_before_export()
    ├─ genesis anchor == Block 0
    ├─ verify_chain() — abort exit 1 on fail
    └─ verify_lamport_monotonic()
         │
         ▼
  canonical JSON files (sorted keys)
         │
         ▼
  deterministic_tarball() — uid/gid/mtime=0, sorted paths
         │
         ▼
  audit_bundle.tar + .sha256 sidecar
```

**Commands:**

```bash
compliance-log export --database data/compliance_ledger.sqlite
compliance-log export --repro-check   # F9 gate
./scripts/export_audit.sh data/inst_ledger.sqlite ./audit_bundle ./audit_bundle.tar
python3 -m inst_spine.export_cli data/ledger.sqlite --repro-check
```

**Promotion:** External auditor replays bundle without vendor call; `repro-check` passes.

---

## What NOT to do

1. **Don't** pitch HIBS £450k on logs alone — pitch ARR or IP floor £40k–£70k
2. **Don't** sell Inst++ as one mega-portfolio — four buyers, four listings
3. **Don't** build Alt-Data feed #2 before feed #1 hits ≥95% coverage 30 days
4. **Don't** duplicate Trading Core as product #5 — it's Proxy-Risk
5. **Don't** parallelize products — one to P2 before starting next

---

## Recommended next 30 days

| Week | HIBS | Inst++ |
|------|------|--------|
| 1–2 | Public paper-trade verifier page | Compliance P2 auditor dry-run |
| 2–3 | Outreach: 3 syndicates for beta JSON feed | Proxy-Risk upstream forward |
| 3–4 | First paid beta (£500 flat) OR honest IP floor decision | Alt-Data: pick **one** target URL |

**North star:** £2k MRR anywhere (HIBS data **or** Inst++ compliance license) beats another month of unmonetised perfection.

---

## Related docs

- `docs/NEW_PRODUCT_INST_PLUS_ROADMAPS.md` — technical roadmaps v3
- `docs/PORTFOLIO_DEEP_DIVE.md` — racing gate lanes
- `src/inst_spine/export.py` — P2 bundle implementation
