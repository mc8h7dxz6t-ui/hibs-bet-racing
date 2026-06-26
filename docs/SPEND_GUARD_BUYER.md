# Spend Guard — Buyer Sheet

**One job:** Reserve-before-dispatch API spend wallet — hold budget before upstream clears, settle on actual cost, lock on spend drift.

**Pitch:** *LiteLLM governs traffic; Spend Guard governs money.*

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| AI platform / FinOps | Weekend LLM spend runaway | **Reserve → settle** on every call |
| Fintech API ops | Double dispatch on retry | Idempotent `request_id` holds |
| CFO / platform sponsor | Budget tracking ≠ budget enforcement | **Drift lockout** freezes wallet |

**Price band:** £2,500–£5,000/mo per tenant (VPC license).

---

## Tech edge (proof)

| Capability | Evidence |
|------------|----------|
| Reserve before dispatch | SQLite IMMEDIATE transactions |
| Settle actual vs estimate | Hold release + balance debit |
| Drift lockout | `DRIFT_THRESHOLD_EXCEEDED` → wallet locked |
| Genesis audit | `spend_guard` events on chain |
| ModelGovernor 8b | **Canonical CLI** for LLM spend plane until Postgres stack in CI |

**Auditor dry-run:**
```bash
./scripts/demo_spend_guard.sh
spend-guard verify-bundle --tarball ./data/demo/spend_guard_bundle.tar
```

---

## 60-second demo

```bash
./scripts/demo_spend_guard.sh
```

---

## Non-goals

- Not full LiteLLM/Portkey proxy (pairs with them)
- Not multi-currency treasury
- Postgres HA wallet = design partner SOW (`make demo-gold` north star)

---

## CLI

| Command | Purpose |
|---------|---------|
| `init-wallet` | Create spend wallet |
| `reserve` / `settle` | Two-phase spend commit |
| `demo-drift-lock` | Drift lockout drill |
| `check` / `export` / `verify-bundle` | Institutional audit |

**Sales spec:** `docs/SPEND_GUARD_SALES_TECH_SPEC.md`  
**North star:** `docs/MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md` (8b spend plane)
