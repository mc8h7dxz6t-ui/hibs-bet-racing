# Drift Gate — Sales & Technical Specification

**Product:** Drift Gate (Phase 2)  
**SKU:** `drift-gate`  
**Version:** Industry gold — PSI/KS enforce gate + Proxy-Risk integration  
**Audience:** Model risk, ML platform, regulated lending, procurement, auditors

---

## Executive summary

**One job:** Compare live **model feature vectors** against an approved baseline using **PSI and Kolmogorov–Smirnov** statistics — **shadow** (log only) or **enforce** (reject/kill) — with **tamper-evident audit** on `inst_spine`.

**One-line pitch:** *Drift that blocks traffic, not drift that emails someone.*

| | |
|---|---|
| **Price band** | £1,500–£3,500/mo per gateway |
| **Default mode** | Shadow (30-day burn-in recommended) |
| **Enforce mode** | REJECT or KILL on PSI ≥ threshold or KS exceeded |
| **Proof** | Every evaluation on genesis chain + offline `verify-bundle` |

---

## Problem → solution

| Buyer pain | Industry default | Drift Gate |
|------------|------------------|------------|
| Model drift discovered Monday | Weekly batch reports | **Real-time gate** on inference path |
| Observability only | Charts and alerts | **Fail-closed enforce** |
| No audit trail on drift decision | Ticket + email | **`drift_gate_evaluation` on chain** |
| Multi-instance state | Per-pod memory | **Redis rolling windows** |
| Auditor distrust | SaaS dashboard | **Offline `verify-bundle`** |

---

## Competitive positioning

| Capability | Fiddler / Arize / WhyLabs | Proxy-only Z-score | **Drift Gate** |
|------------|---------------------------|-------------------|----------------|
| PSI / KS drift | Yes (platform) | No | **Yes (gate)** |
| Block inference | Rare | Price only | **Feature vector enforce** |
| Offline verify | No | No | **`verify-bundle`** |
| Air-gap VPC | SaaS | Partial | **Default** |
| Proxy integration | SDK | Native | **`PROXY_DRIFT_BASELINE`** |

---

## Architecture

```
feature_vector (HTTP / proxy body)
        │
        ▼
┌───────────────────┐
│  Rolling window   │  file or Redis per model_id
│  + baseline       │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  PSI + KS         │  per feature, configurable thresholds
└─────────┬─────────┘
          │
    shadow │ enforce
          ▼
┌───────────────────┐
│  AppendOnlyLedger │  drift_gate_evaluation events
└───────────────────┘
```

### PSI bands (industry standard)

| PSI | Band |
|-----|------|
| &lt; 0.10 | Stable |
| 0.10 – 0.25 | Watch |
| ≥ 0.25 | Significant — enforce triggers |

---

## Integration

### Standalone CLI
```bash
drift-gate baseline --model-id credit-v3 --features '{"income":50000}' \
  --out baseline.json --synthetic --samples 100
drift-gate evaluate --baseline baseline.json --features '{"income":180000}' --mode enforce
```

### Proxy-Risk (drop-in)
```bash
export PROXY_DRIFT_BASELINE=./baseline.json
export PROXY_DRIFT_MODE=shadow
proxy-risk evaluate --body '{"features":{"income":50000,"debt_ratio":0.35}}'
```

### Python hook
```python
from drift_gate.integrate import evaluate_model_features
```

---

## Institutional proof

| Check | Command |
|-------|---------|
| Unit tests | `pytest tests/test_drift_gate.py` |
| Rigorous E2E | `scripts/instpp_rigorous_test.sh` (Phase 2 section) |
| Demo | `scripts/demo_drift_gate.sh` |
| Chaos | `scripts/chaos_instpp.sh` (rolling state persistence) |

---

## Explicit non-goals

- Not MLOps UI or experiment tracking
- Not protected-attribute fairness certification
- Not sub-5ms HFT path (Python hot path; Go adapter = design partner SOW)
