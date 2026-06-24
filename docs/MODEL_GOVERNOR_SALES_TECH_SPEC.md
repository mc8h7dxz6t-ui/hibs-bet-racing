# ModelGovernor — Sales & Technical Specification

**Product:** ModelGovernor (#8)  
**SKU:** `model-governor`  
**Version:** Gold standard (model lifecycle ledger, offline verify-bundle)  
**Audience:** ML platform teams, model risk management, legal, procurement, auditors

---

## Executive summary

**One job:** Record every **ML model governance event** (register, approve, deploy, retire, drift alert) with a **model snapshot**, **outcome**, and **tamper-evident cryptographic chain** that a third party can verify **offline — without calling the vendor**.

**One-line pitch:** *Prove which model version was approved for production on date X — with math, not a spreadsheet.*

| | |
|---|---|
| **Price band** | £400–£1,000/mo per tenant |
| **Deploy** | Air-gapped VPC / on-prem — SQLite + WAL |
| **Proof** | Genesis-anchored hash chain + deterministic audit tarball |
| **Demo** | 60 seconds CLI |

---

## Problem → solution

| Buyer pain | Industry default | ModelGovernor |
|------------|------------------|---------------|
| "Who approved model v3.2.1?" | Spreadsheet / Jira export | `approve` event + model snapshot on chain |
| Registry logs are editable | SaaS dashboard trust | Offline `verify-bundle` on tarball only |
| Generic compliance tool | Custom fields for models | **First-class model snapshot contract** |
| Deploy without audit trail | CI/CD logs (mutable) | `deploy` event with artifact hash |
| Drift dispute evidence | Alert email only | `drift_alert` event sealed on ledger |
| Reproducibility disputes | Non-deterministic exports | F9 — identical ledger → identical bundle SHA256 |

---

## Ideal buyer

| Segment | Use case | Why us |
|---------|----------|--------|
| **ML platform / MLOps** | Model registry audit spine | Governance events without full MLOps lock-in |
| **Model risk (MRM)** | SR 11-7 / internal model validation | Approve/deploy proof with artifact hash |
| **Regulated lending / insurtech** | Credit model governance | Air-gap deploy; buyer holds ledger |
| **Legal / compliance** | Dispute on production model version | Offline auditor replay |

**Win when:** buyer needs **model-specific governance proof**, not generic GRC or full MLOps.  
**Lose when:** buyer needs MLflow UI, experiment tracking, or hosted model serving.

---

## Competitive positioning

| Capability | MLflow Registry | GRC SaaS | **ModelGovernor** |
|------------|-----------------|----------|-------------------|
| Model snapshot contract | Tags/params | Custom fields | **First-class ingest contract** |
| Approve/deploy audit trail | Version history | Case workflow | **Genesis chain per event** |
| Offline auditor replay | Needs server | No | **`verify-bundle` tarball only** |
| Deterministic export hash | No | No | **F9 reproducibility gate** |
| Air-gap deploy | Rare | SaaS | **Default architecture** |
| Drift alert as sealed event | Metrics only | Alert ticket | **`drift_alert` on chain** |

---

## Architecture

```
model_snapshot + action + outcome
        │
        ▼
┌───────────────────┐
│  record           │  register / approve / deploy / retire / drift_alert
│  (model_governor) │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  AppendOnlyLedger │  genesis block 0 + hash chain + Lamport seq
│  (inst_spine)     │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  check F1–F9      │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  export           │  deterministic tar + SHA256 sidecar
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  verify-bundle    │  auditor dry-run (no live DB)
└───────────────────┘
```

### Model snapshot contract

Required: `model_id`, `version`, `artifact_hash`, `risk_tier`

```json
{
  "model_id": "credit-risk-v3",
  "version": "3.2.1",
  "artifact_hash": "sha256:abc123...",
  "risk_tier": "high",
  "framework": "xgboost",
  "metrics": {"auc": 0.84, "psi": 0.03},
  "training_data_ref": "dataset-2026-q1"
}
```

### Governance actions

| Action | Typical use |
|--------|-------------|
| `register` | New model version enters registry |
| `approve` | Model risk / compliance sign-off |
| `reject` | Blocked from production |
| `deploy` | Promoted to production environment |
| `retire` | Decommissioned |
| `drift_alert` | PSI / performance drift recorded |

---

## CLI reference

```bash
pip install -e ".[dev,instpp]"
```

| Command | Purpose |
|---------|---------|
| `model-governor record --action ACTION --model JSON [--outcome JSON] [--actor NAME] [--database PATH]` | Log governance event |
| `model-governor check [--database PATH]` | Run F1–F9 institutional check |
| `model-governor export [--database PATH] [--tarball PATH] [--repro-check]` | Deterministic audit bundle |
| `model-governor verify-bundle --tarball PATH` | Offline auditor replay |

---

## Proof & diligence

```bash
./scripts/demo_model_governor.sh
./scripts/instpp_rigorous_test.sh
model-governor verify-bundle --tarball ./model_governor_bundle.tar
```

| Artifact | Path |
|----------|------|
| Rigorous test log | `docs/test_logs/instpp_rigorous_latest.log` |
| Buyer one-pager | `docs/MODEL_GOVERNOR_BUYER.md` |
| Architecture | `src/model_governor/README.md` |

---

## Non-goals (say no in RFPs)

- Not a full MLOps platform (MLflow, W&B, SageMaker, Vertex)
- Not model training, feature store, or experiment UI
- Not real-time drift detection service (records events; buyer wires monitors)
- Not LLM safety inference (NeMo/Bedrock upstream)
- Not bundled with HIBS sports products

---

## Pricing & packaging

| Tier | Band | Includes |
|------|------|----------|
| **Tenant license** | £400–£1,000/mo | CLI + spine + export + verify-bundle |
| **Implementation** | Custom SOW | CI/CD hook mapping, MRM onboarding |
| **Bundle with Compliance Logger** | 15% discount | Same buyer, decision + model threads |
| **Maintenance** | 15–20% ARR | Security patches, spine upgrades |

---

## RFP quick answers

| Question | Answer |
|----------|--------|
| Tamper-proof model approval audit trail? | **Yes** |
| Offline third-party verification? | **Yes** — `verify-bundle` |
| Air-gapped deploy? | **Yes** |
| Prove model vX deployed on date Y? | **Yes** — snapshot + deploy event + export |
| Full MLOps experiment tracking? | **No** |
| Hosted model serving? | **No** |

---

## Related documents

- `docs/MODEL_GOVERNOR_BUYER.md` — one-page buyer sheet  
- `docs/PORTFOLIO_SALES_SHEET.md` — portfolio pricing matrix  
- `docs/BUYER_EVIDENCE_PACK.md` — procurement dry-run  
- `docs/COMPLIANCE_LOGGER_SALES_TECH_SPEC.md` — generic decision audit (#1)
