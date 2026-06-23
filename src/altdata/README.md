# Alt-Data Extractor (`altdata`)

One clean telemetry feed — field coverage ladder, structural rescue, genesis ledger per poll.

## Architecture

```
poll → field ladder (primary → fallback → rescue) → coverage % → ledger append
                                                              → check → export → verify-bundle
```

## Install

```bash
pip install -e ".[dev,instpp]"
```

## CLI

```bash
altdata poll --feed demo_feed --ctx '{"demo_price":42.5,"demo_seats":180}'
altdata poll --url https://httpbin.org/json --feed live_feed
altdata check --database data/altdata_demo.sqlite
altdata export --database data/altdata_demo.sqlite --tarball altdata_bundle.tar
altdata verify-bundle --tarball altdata_bundle.tar
```

## Demo

```bash
./scripts/demo_altdata.sh
```

## Buyer positioning

`docs/ALTDATA_BUYER.md`

## Gold standard

`docs/INSTITUTIONAL_STANDARD.md`
