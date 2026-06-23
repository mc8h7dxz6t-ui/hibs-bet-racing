# Ad Guard (`ad_guard`)

Marketing API spend guardrail — per-campaign bucket, Z-score kill, genesis audit before upstream.

## Architecture

```
spend request → circuit → schema → bucket → idempotency → z-score → [shadow | live httpx]
                      ↓ every APPROVE / REJECT / KILL logged
```

## Install

```bash
pip install -e ".[dev,instpp]"
```

## CLI

```bash
ad-guard evaluate --provider google --body '{"campaignId":"12345","bidMicros":2500000}'
ad-guard serve --port 8788
ad-guard check --database data/ad_guard_ledger.sqlite
ad-guard export --database data/ad_guard_ledger.sqlite --tarball ad_guard_bundle.tar
ad-guard verify-bundle --tarball ad_guard_bundle.tar
```

## Environment

| Variable | Purpose |
|----------|---------|
| `AD_GUARD_UPSTREAM_BASE` | Live marketing API base URL |
| `AD_GUARD_REQUIRE_CREATIVE_APPROVAL` | Require NeMo/safety approval headers |
| `INST_REDIS_URL` | Multi-instance idempotency |

## Demo

```bash
./scripts/demo_ad_guard.sh
```

## Buyer positioning

`docs/AD_GUARD_BUYER.md`

## Gold standard

`docs/INSTITUTIONAL_STANDARD.md`
