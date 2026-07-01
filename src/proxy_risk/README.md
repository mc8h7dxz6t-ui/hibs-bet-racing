# Proxy-Risk Gateway (`proxy_risk`)

Outbound API circuit breaker with genesis-anchored audit trail.

## Architecture

```
client intent → gate chain (memory) → [shadow | live httpx forward]
                      ↓
              AppendOnlyLedger (every outcome logged)
```

## Install

```bash
pip install -e ".[dev,instpp]"
```

## Serve (production HTTP)

```bash
export PROXY_RISK_DATABASE=data/proxy_risk.sqlite
export PROXY_RISK_SHADOW=1
export PROXY_RISK_API_KEY=your-vpc-key   # optional local dev if unset
python -m proxy_risk.serve
# GET /health  GET /ready  POST /v1/evaluate
```

Legacy aiohttp demo: `proxy-risk serve` (uses `PROXY_RISK_API_TOKEN`).

## CLI

```bash
proxy-risk evaluate --client-id broker-1 --body '{"symbol":"AAPL"}'
proxy-risk evaluate --live --path /post --body '{"ok":true}'  # needs PROXY_RISK_UPSTREAM_BASE
proxy-risk check --database data/proxy_risk_ledger.sqlite
proxy-risk export --repro-check
proxy-risk verify-bundle --tarball proxy_audit.tar
proxy-risk serve --port 18443
```

## Demo

```bash
./scripts/demo_proxy_risk.sh
```

## Buyer positioning

`docs/PROXY_RISK_BUYER.md`

## Gold standard

`docs/INSTITUTIONAL_STANDARD.md`
