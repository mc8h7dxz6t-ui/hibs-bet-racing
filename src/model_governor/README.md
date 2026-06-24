# ModelGovernor

**One job:** Tamper-proof **ML model lifecycle governance** — register, approve, deploy, and retire models with cryptographic proof an auditor can verify offline.

## Positioning

| Product | Scope |
|---------|-------|
| **ModelGovernor (#8)** | Model registry + approval/deploy/retire events |
| Compliance Logger (#1) | Generic regulated business decisions |
| AI Kit (#4) | Agent step traces + checkpoints |

## Quick start

```bash
pip install -e ".[dev,instpp]"

model-governor record \
  --action register \
  --model docs/demo_model_snapshot.json \
  --outcome '{"status":"registered","ref":"mg-001"}'

model-governor record \
  --action approve \
  --model docs/demo_model_snapshot.json \
  --outcome '{"status":"approved","approver":"risk-board"}' \
  --actor risk-board

model-governor check
model-governor export --tarball ./model_governor_bundle.tar
model-governor verify-bundle --tarball ./model_governor_bundle.tar
```

## Governance actions

`register` · `approve` · `reject` · `deploy` · `retire` · `drift_alert`

## Model snapshot contract

Required fields: `model_id`, `version`, `artifact_hash`, `risk_tier`

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

## Demo

```bash
./scripts/demo_model_governor.sh
```

**Buyer doc:** `docs/MODEL_GOVERNOR_BUYER.md`  
**Sales spec:** `docs/MODEL_GOVERNOR_SALES_TECH_SPEC.md`  
**Strategic positioning & valuation:** `docs/MODEL_GOVERNOR_POSITIONING_AND_VALUATION.md`
