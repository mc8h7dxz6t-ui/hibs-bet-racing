# Drift Gate — Outbound Model Bias & Regulatory Drift Interceptor

PSI/KS statistical drift gate with shadow → enforce modes and genesis audit.

## One job

Block or shadow-log model inference when feature distributions drift from approved baseline.

## Quick start

```bash
pip install -e ".[dev,instpp]"

# Build baseline (synthetic demo)
drift-gate baseline --model-id credit-v3 --features '{"income":50000,"debt_ratio":0.35}' \
  --out data/demo/drift_baseline.json --synthetic --samples 100

# Shadow evaluate (always approves, logs drift)
drift-gate evaluate --baseline data/demo/drift_baseline.json \
  --features '{"income":120000,"debt_ratio":0.85}' --mode shadow

# Enforce + ledger
drift-gate evaluate --baseline data/demo/drift_baseline.json \
  --features '{"income":120000,"debt_ratio":0.85}' --mode enforce \
  --database data/drift_gate.sqlite

drift-gate check --database data/drift_gate.sqlite
drift-gate export --database data/drift_gate.sqlite --tarball data/drift_gate_bundle.tar
drift-gate verify-bundle --tarball data/drift_gate_bundle.tar
```

## Integration

```python
from drift_gate.integrate import evaluate_model_features

result = evaluate_model_features(
    model_id="credit-v3",
    version="v1",
    features={"income": 50000, "debt_ratio": 0.35},
    baseline_path=Path("data/drift_baseline.json"),
    mode="shadow",
)
```

Plugs in front of Proxy-Risk upstream or ModelGovernor deploy gate.

## Non-goals

- Not a full MRM platform (Fiddler/Arize replacement)
- Not fairness certification — provides evidence + enforcement hook
- Not real-time training pipeline monitoring
