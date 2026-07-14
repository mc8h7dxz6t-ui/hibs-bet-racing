# Webhook Replay — Buyer Sheet

**One job:** Capture raw webhook ingress bytes, replay offline without network, prove idempotent outcomes with genesis audit.

**Pitch:** *Replay the exact bytes that caused the duplicate charge dispute.*

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| Fintech / SaaS billing | Webhook dispute — what bytes arrived? | `.wrcap` mmap capture + SHA256 manifest |
| Platform engineering | Can't reproduce prod ingress locally | Air-gapped replay engine |
| Compliance / legal | Auditor needs offline proof | `webhook_replay` events on genesis chain |


---

## Tech edge (proof)

| Capability | Evidence |
|------------|----------|
| Byte-identical capture | `WRCAP` format — mmap-readable |
| Air-gapped replay | No network in replay mode |
| Tamper detection | `payload_sha256` diff on replay |
| Mesh integration | `WEBHOOK_REPLAY_CAPTURE_DIR` on Webhook Mesh |
| Offline proof | `export` + `verify-bundle` |

**Auditor dry-run:**
```bash
./scripts/demo_webhook_replay.sh
webhook-replay verify-bundle --tarball ./data/demo/webhook_replay_bundle.tar
```

---

## 60-second demo

```bash
./scripts/demo_webhook_replay.sh
```

---

## Non-goals

- Not webhook delivery platform (Hookdeck, Svix)
- Not Kafka-scale streaming
- Dead-letter poison replay stays in `webhook-mesh replay`

---

## Environment

| Variable | Purpose |
|----------|---------|
| `WEBHOOK_REPLAY_CAPTURE_DIR` | Auto-capture on Webhook Mesh ingress |

---

## CLI

| Command | Purpose |
|---------|---------|
| `capture` | Store one webhook for offline replay |
| `replay` | Replay one or all captures (air-gapped) |
| `check` / `export` / `verify-bundle` | Institutional audit |

**Sales spec:** `docs/WEBHOOK_REPLAY_SALES_TECH_SPEC.md`
