# Webhook Replay — Deterministic Time-Travel Debugger

Byte-identical webhook capture and air-gapped replay with genesis audit.

## One job

Capture raw ingress bytes, replay offline without network, prove idempotent outcomes.

## Quick start

```bash
pip install -e ".[dev,instpp]"

echo '{"id":"evt-1","amount":999}' > /tmp/body.json

webhook-replay capture --capture-id evt-1 --body-file /tmp/body.json \
  --header "X-Webhook-Id:evt-1" --store-dir data/demo/captures

webhook-replay replay --capture-id evt-1 --store-dir data/demo/captures \
  --database data/webhook_replay.sqlite

webhook-replay export --database data/webhook_replay.sqlite --tarball data/webhook_replay_bundle.tar
webhook-replay verify-bundle --tarball data/webhook_replay_bundle.tar
```

## Integration with Webhook Mesh

```python
from webhook_replay.integrate import capture_from_ingress

capture_from_ingress(
    capture_id=webhook_id,
    tenant_id=tenant,
    body=raw_body,
    headers=dict(request.headers),
    store_dir=Path("data/captures"),
)
```

Call after HMAC verify, before HTTP 200 — complements Webhook Mesh WAL.

## Non-goals

- Not a webhook delivery platform (Hookdeck/Svix)
- Not Kafka-scale streaming
- Dead-letter poison replay stays in `webhook-mesh replay`
