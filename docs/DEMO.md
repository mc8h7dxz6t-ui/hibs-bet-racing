# Inst++ Demo — Compliance Logger + Proxy-Risk

**One command** runs both gold-standard product demos and writes proof artifacts to `data/demo/`.

## Quick start

```bash
pip install -e ".[dev,instpp]"
chmod +x scripts/demo_instpp.sh scripts/demo_*.sh
./scripts/demo_instpp.sh
```

That's it. ~30–60 seconds depending on network (live httpbin forward).

## What it does

| Step | Product | Action |
|------|---------|--------|
| 1 | **Compliance Logger** | Ingest decision → verify chain → F1–F9 check → export → offline verify-bundle |
| 2 | **Proxy-Risk** | Shadow gates → idempotency proof → live forward → check → export → verify-bundle |

## Artifacts (after demo)

```
data/demo/
├── compliance.sqlite
├── compliance_bundle.tar          (+ .sha256 sidecar)
├── proxy.sqlite
└── proxy_bundle.tar               (+ .sha256 sidecar)
```

Auditors can replay bundles **without your database**:

```bash
compliance-log verify-bundle --tarball data/demo/compliance_bundle.tar
proxy-risk verify-bundle --tarball data/demo/proxy_bundle.tar
```

## Options

```bash
./scripts/demo_instpp.sh --help     # usage
./scripts/demo_instpp.sh --clean    # wipe data/demo first
SKIP_LIVE=1 ./scripts/demo_instpp.sh   # offline / no httpbin
```

## Run individually

```bash
./scripts/demo_compliance_logger.sh
./scripts/demo_proxy_risk.sh
```

## Demo payloads

- `docs/demo_snapshot.json` — compliance decision input
- `docs/demo_proxy_request.json` — proxy order request

## Full test + log (pre-sales)

```bash
./scripts/instpp_rigorous_test.sh
# → docs/test_logs/instpp_rigorous_latest.log
```

## More

- `docs/INST_PLUS_GOLD_STANDARD.md` — quality bar
- `docs/INST_PLUS_DEEP_DIVE_COMPLIANCE_PROXY.md` — industry positioning
