# Webhook Idempotency Mesh (`webhook_mesh`)

Inbound webhook signature verify, idempotency CAS, WAL-before-ack, async forward with genesis ledger.

## Architecture

```
POST /v1/ingress/{tenant} → HMAC → Redis idempotency → WAL fsync → 200 OK → queue → forward
Stripe route: POST /v1/ingress/stripe/{tenant}
Shopify route: POST /v1/ingress/shopify/{tenant}
```

## Install

```bash
pip install -e ".[dev,instpp]"
```

## CLI

```bash
export WEBHOOK_PROVIDER_SECRET=demo-secret
webhook-mesh serve --port 8787 --ledger data/webhook_mesh_ledger.sqlite
webhook-mesh demo-sign --secret demo-secret --body-file payload.json
webhook-mesh check --database data/webhook_mesh_ledger.sqlite
webhook-mesh export --database data/webhook_mesh_ledger.sqlite --tarball webhook_bundle.tar
webhook-mesh verify-bundle --tarball webhook_bundle.tar
```

## Demo

```bash
./scripts/demo_webhook_mesh.sh
```

## Buyer positioning

`docs/WEBHOOK_MESH_BUYER.md`

## Gold standard

`docs/INSTITUTIONAL_STANDARD.md`
