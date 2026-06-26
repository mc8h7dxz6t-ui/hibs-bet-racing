# ModelGovernor — Buyer Sheet

**One job:** Tamper-proof ML model lifecycle governance — register, approve, deploy, and retire models with cryptographic proof an auditor can verify offline.

**Pitch:** *Prove which model version was approved for production on date X — with math, not a spreadsheet.*

> **LLM spend control plane:** Canonical sales demo is **`make demo-gold`** (11 steps, drift lockout in step 10). See [DEMO_GOLD.md](DEMO_GOLD.md) and [MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md](MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md). This buyer sheet covers the **#8 lifecycle CLI** SKU on `inst_spine`.

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| ML platform / MLOps | Model registry logs are editable | Genesis-anchored hash chain + export bundle |
| Risk / model validation | "Who approved v3.2.1 for prod?" | `approve` / `deploy` events with model snapshot |
| Regulated lending / insurtech | SR 11-7 / model risk evidence | Offline `verify-bundle` without vendor callback |
| Legal / compliance | Conflated with generic GRC | Model-specific snapshot contract |

**Price band:** £400–£1,000/mo per tenant (model registry + governance ledger).

---

## Tech edge (proof)

| Gate | Evidence |
|------|----------|
| F1–F2 | Model snapshot completeness + manifest linkage |
| F3–F4 | Hash chain + Lamport monotonicity |
| F7 | Required field coverage on `model_snapshot` |
| F9 | Identical ledger → identical bundle SHA256 |
| Actions | `register` · `approve` · `reject` · `deploy` · `retire` · `drift_alert` |

**Auditor dry-run:**
```bash
model-governor record --action register --model docs/demo_model_snapshot.json
model-governor export --database ./model_governor.sqlite --tarball ./model_governor_bundle.tar
model-governor verify-bundle --tarball ./model_governor_bundle.tar
```

---

## 60-second demo

**Lifecycle CLI (#8):**

```bash
./scripts/demo_model_governor.sh
```

**LLM spend control plane (canonical sales):**

```bash
make demo-gold-up && make demo-gold
```

See [DEMO_GOLD.md](DEMO_GOLD.md) — drift lockout is step 10; use `make demo-gold-reset` before rerun.

---

## Non-goals

- Not a full MLOps platform (MLflow, Weights & Biases, SageMaker)
- Not model training, feature store, or experiment tracking UI
- Not real-time drift monitoring service (records `drift_alert` events only)
- Not NeMo / LLM safety inference (see Ad Guard / AI Kit upstream)

---

## CLI

| Command | Purpose |
|---------|---------|
| `record` | Log governance event (register/approve/deploy/…) |
| `check` | Run F1–F9 institutional check |
| `export` | Deterministic audit bundle |
| `verify-bundle` | Offline auditor replay |

See `src/model_governor/README.md` for architecture.  
**Full spec:** `docs/MODEL_GOVERNOR_SALES_TECH_SPEC.md`  
**Strategic comps & valuation:** `docs/MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md`  
**Gold demo:** `docs/DEMO_GOLD.md` — `make demo-gold`

---

## Next step

| Step | Action |
|------|--------|
| 1 | `./scripts/demo_model_governor.sh` (60s) |
| 2 | `model-governor verify-bundle --tarball ./model_governor_bundle.tar` |
| 3 | RFP depth → `docs/MODEL_GOVERNOR_SALES_TECH_SPEC.md` |
| 4 | Portfolio pricing → `docs/PORTFOLIO_SALES_SHEET.md` |
