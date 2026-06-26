# ModelGovernor — Gold Demo (canonical sales walkthrough)

**Purpose:** Institutional++ sales demo — governance + reliability on the full stack (gateway + sidecar + reconciler).  
**Stack:** `docker-compose.demo.yml`

---

## Canonical flow (use this)

```bash
make demo-gold-up
make demo-gold          # full 11-step walkthrough
make demo-gold-reset    # before rerun (wallet locked after step 10)
make demo-gold-down     # teardown
```

**Sales / diligence:** `make demo-gold` is the single canonical proof. You do **not** need `make demo-drift-lock` for the sales story.

---

## What `make demo-gold` covers (11 steps)

| Step | Theme |
|------|--------|
| 1–9 | Reserve → dispatch → settle, reconciler, multi-provider gateway semantics |
| **10** | **Drift lockout** — `DRIFT_THRESHOLD_EXCEEDED` → wallet locked → **409** on next reserve |
| 11 | Wrap-up / audit surface |

After step 10 the wallet is locked. Run `make demo-gold-reset` before the next full walkthrough.

---

## Demo commands reference

| Command | Stack | Purpose |
|---------|-------|---------|
| `make demo-gold-up` | `docker-compose.demo.yml` (gateway + sidecar + reconciler) | Start gold stack |
| `make demo-gold` | Gold stack | **Canonical sales demo** — governance + reliability, drift in step 10 |
| `make demo-gold-reset` | Gold stack | Reset wallet state after drift lockout |
| `make demo-gold-down` | Gold stack | Teardown |
| `make demo-drift-lock` | `docker-compose.yml` (sidecar only, legacy) | Optional sidecar-only drift drill — **not** part of gold walkthrough |
| `make demo-up` | `docker-compose.yml` (basic) | Legacy basic stack — only if running `demo-drift-lock` standalone |

---

## When to use `make demo-drift-lock`

Only if you want a **standalone** drift demo on the basic stack (no gateway):

```bash
make demo-up            # not demo-gold-up
make demo-drift-lock
```

**Redundant** if you already ran `make demo-gold` — drift is included in step 10.

---

## Portfolio CLI demo (#8 lifecycle SKU)

For the **model lifecycle governance** ledger (register / approve / deploy / `verify-bundle`) on `inst_spine`:

```bash
./scripts/demo_model_governor.sh
model-governor verify-bundle --tarball ./model_governor_bundle.tar
```

That is a separate 60-second CLI proof — complementary to, not a substitute for, `make demo-gold`.

---

## Related

- [MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md](MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md) — comps, exit framing
- [MODEL_GOVERNOR_BUYER.md](MODEL_GOVERNOR_BUYER.md) — buyer one-pager
