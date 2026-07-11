# Drift Gate — Buyer Sheet

**One job:** PSI/KS statistical drift interceptor on model feature vectors — shadow burn-in, then enforce reject/kill with genesis audit.

**Pitch:** *Block drifted inference before the regulator calls — with math, not a dashboard.*

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| Regulated lending / insurtech | Model bias drift over a weekend | PSI/KS gate on live feature vectors |
| ML platform / MRM | Observability alerts too late | **Enforce mode** rejects traffic, not email only |
| Model risk / legal | Dispute on production model inputs | `drift_gate_evaluation` events on genesis chain |


---

## Tech edge (proof)

| Capability | Evidence |
|------------|----------|
| PSI + KS per feature | Industry-standard stability metrics |
| Shadow → enforce | Burn-in without blocking production |
| Rolling state persistence | File or Redis (`INST_REDIS_URL`) |
| Proxy integration | `PROXY_DRIFT_BASELINE` on Proxy-Risk |
| Offline proof | `export` + `verify-bundle` |

**Auditor dry-run:**
```bash
./scripts/demo_drift_gate.sh
drift-gate verify-bundle --tarball ./data/demo/drift_gate_bundle.tar
```

---

## 60-second demo

```bash
./scripts/demo_drift_gate.sh
```

---

## Non-goals

- Not full MRM platform (Fiddler, Arthur, Arize replacement)
- Not fairness certification — evidence + enforcement hook
- Not training pipeline monitoring

---

## Environment

| Variable | Purpose |
|----------|---------|
| `INST_REDIS_URL` | Multi-instance rolling feature windows |
| `PROXY_DRIFT_BASELINE` | Enable drift gate on Proxy-Risk hot path |
| `PROXY_DRIFT_MODE` | `shadow` or `enforce` |

---

## CLI

| Command | Purpose |
|---------|---------|
| `baseline` | Create feature baseline (synthetic or sample) |
| `evaluate` | Run PSI/KS gate on feature vector |
| `check` | F1–F9 institutional check |
| `export` / `verify-bundle` | Offline auditor replay |

**Sales spec:** `docs/DRIFT_GATE_SALES_TECH_SPEC.md`
