# Health Telemetry Recorder (`health_telemetry`)

Device telemetry batch ingest on institutional spine — schema contract, per-device sequence gate, optional WAL-before-ack HTTP ingress, F1–F9, offline verify.

## Architecture

```
CLI or POST /v1/telemetry/batch
  → [HTTP] ingress WAL fsync
  → schema validate (ts, seq, profile fields) + F7 coverage
  → per-device sequence gate (gap/backward fail-closed)
  → ledger append (telemetry_batch + packet_summaries)
  → check → export [--observation-lane] → verify-bundle
```

## Install

```bash
pip install -e ".[dev,instpp]"
```

## CLI

```bash
health-telemetry ingest --device-id ward-7 \
  --packets '[{"ts":"2026-06-01T12:00:00Z","seq":1,"hr":72,"spo2":98}]'
health-telemetry serve
health-telemetry check --database data/health_telemetry.sqlite
health-telemetry export --database data/health_telemetry.sqlite --tarball health_bundle.tar
health-telemetry export --observation-lane --tarball health_obs.tar
health-telemetry verify-bundle --tarball health_bundle.tar
```

## Integration

```python
from health_telemetry.integrate import ingest_device_batch
```

## Demo

```bash
./scripts/demo_health_telemetry.sh
make health-telemetry-serve
```

## HIPAA diligence

`docs/HEALTH_TELEMETRY_HIPAA_PACK.md` (template — not certification)

## Buyer positioning

`docs/HEALTH_TELEMETRY_BUYER.md` · `docs/HEALTH_TELEMETRY_SALES_TECH_SPEC.md`

## Gold standard

`docs/INST_PLUS_GOLD_STANDARD.md`
