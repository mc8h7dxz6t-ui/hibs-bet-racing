# Gold Demo — Spend-plane sales walkthrough (shipped CLI)

**Purpose:** Canonical **LLM spend governance** demo for platform / FinOps buyers.  
**Proof:** `make demo-gold` — 11-step Spend Guard CLI walkthrough with offline `verify-bundle`.

> **Honest scope:** This is the **shipped** sales demo. A Postgres gateway + sidecar + reconciler compose stack is a design-partner north star — not required for diligence. Lead with this CLI proof.

---

## Canonical flow (use this)

```bash
make install
make demo-ready
make demo-gold              # full 11-step walkthrough
make demo-gold-reset        # before rerun (wallet locked after step 10)
make demo-gold-up           # optional: Compliance + Proxy workflow UI
make demo-gold-down         # stop workflow UI
```

**Sales / diligence:** `make demo-gold` is the single canonical spend-plane proof. Full portfolio (all 11 SKUs): `make demo-all`.

---

## What `make demo-gold` covers (11 steps)

| Step | Theme |
|------|--------|
| 1 | Init platform wallet (£1000 budget) |
| 2 | Shadow burn-in (reserve without debit) |
| 3–4 | Provider A — reserve → settle |
| 5–6 | Provider B — reserve → settle |
| 7 | Reconciler mismatch (actual > estimate) |
| 8 | Wallet status (FinOps view) |
| 9 | Normal traffic cycle |
| **10** | **Drift lockout** — `DRIFT_THRESHOLD_EXCEEDED` → wallet locked → blocked reserve |
| 11 | F1–F9 check → export → offline `verify-bundle` |

After step 10 the wallet is locked. Run `make demo-gold-reset` before the next full walkthrough.

---

## Demo commands reference

| Command | Purpose |
|---------|---------|
| `make demo-gold` | **Canonical** spend-plane sales demo (CLI) |
| `make demo-gold-reset` | Wipe spend-gold wallet after drift lockout |
| `make demo-gold-up` | Seed portfolio data + start workflow UI (Compliance + Proxy) |
| `make demo-gold-down` | Stop workflow UI |
| `make demo-all` | All 11 SKU demos → `data/demo/portfolio/` |
| `docker compose -f docker-compose.instpp.yml up` | Optional containerized workflow UI |

---

## ModelGovernor lifecycle CLI (#8)

For **model lifecycle governance** (register / approve / deploy / `verify-bundle`) on `inst_spine`:

```bash
./scripts/demo_model_governor.sh
model-governor verify-bundle --tarball ./data/demo/model_governor_bundle.tar
```

Complementary to `make demo-gold` — buyers evaluating SR 11-7 / model-risk evidence use the **#8 CLI** ledger.

---

## Related

- [RUN_DEMO.md](RUN_DEMO.md) — single entry point for all demos
- [MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md](MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md) — comps, exit framing
- [MODEL_GOVERNOR_BUYER.md](MODEL_GOVERNOR_BUYER.md) — buyer one-pager
- [SPEND_GUARD_BUYER.md](SPEND_GUARD_BUYER.md) — Spend Guard SKU
