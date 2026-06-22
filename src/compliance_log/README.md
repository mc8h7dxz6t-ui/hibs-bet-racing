# Compliance Logger (`compliance_log`)

Tamper-proof decision audit on Inst++ spine.

## Architecture

```
snapshot + outcome → ingest → AppendOnlyLedger (WAL fsync → hash chain)
                                    ↓
                         check (F1–F9) → export → verify-bundle (offline)
```

## Install

```bash
pip install -e ".[dev,instpp]"
```

## CLI

```bash
compliance-log ingest --snapshot docs/demo_snapshot.json --actor demo
compliance-log check --database data/compliance_ledger.sqlite
compliance-log export --repro-check
compliance-log verify-bundle --tarball audit_bundle.tar
```

## Demo

```bash
./scripts/demo_compliance_logger.sh
```

## Buyer positioning

`docs/COMPLIANCE_LOGGER_BUYER.md`

## Gold standard

`docs/INST_PLUS_GOLD_STANDARD.md`
