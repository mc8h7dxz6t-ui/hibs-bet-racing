# Health Telemetry Recorder (`health_telemetry`)

Device telemetry batch ingest on institutional spine — Lamport ordering, F1–F9, offline verify.

## Architecture

```
POST batch → schema validate → ledger append (telemetry_batch) → check → export → verify-bundle
```

## Install

```bash
pip install -e ".[dev,instpp]"
```

## CLI

```bash
health-telemetry ingest --device-id ward-7 --packets '[{"hr":72,"spo2":98}]'
health-telemetry check --database data/health_telemetry.sqlite
health-telemetry export --database data/health_telemetry.sqlite --tarball health_bundle.tar
health-telemetry verify-bundle --tarball health_bundle.tar
```

## Demo

```bash
./scripts/demo_health_telemetry.sh
```

## HIPAA diligence

`docs/HEALTH_TELEMETRY_HIPAA_PACK.md` (template — not certification)

## Buyer positioning

`docs/HEALTH_TELEMETRY_BUYER.md`

## Gold standard

`docs/INSTITUTIONAL_STANDARD.md`
