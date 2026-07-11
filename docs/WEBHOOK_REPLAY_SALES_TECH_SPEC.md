# Webhook Replay — Sales & Technical Specification

**Product:** Webhook Replay (Phase 2)  
**SKU:** `webhook-replay`  
**Version:** Industry gold — mmap capture + deterministic replay  
**Audience:** Fintech platform teams, SaaS billing, procurement, auditors

---

## Executive summary

**One job:** **Capture** raw webhook ingress (headers + body bytes), **replay** deterministically in an air-gapped environment, and **prove** idempotent outcomes on the institutional genesis chain.

**One-line pitch:** *Time-travel debugging for webhooks — with cryptographic proof.*

| | |
|---|---|
| **Capture format** | `.wrcap` — MAGIC + JSON header + raw body (mmap) |
| **Replay** | No network — handler + diff report |
| **Proof** | `webhook_replay` ledger events + offline `verify-bundle` |

---

## Problem → solution

| Buyer pain | Industry default | Webhook Replay |
|------------|------------------|----------------|
| "What bytes caused the double charge?" | App logs (lossy) | **Byte-identical `.wrcap`** |
| Reproduce prod ingress | Staging guesswork | **Offline replay from capture** |
| Audit dispute | Vendor callback | **`verify-bundle` tarball only** |
| Mesh already dedupes | WAL before 200 (#5) | **Replay layer complements Mesh** |

---

## Competitive positioning

| Capability | Hookdeck / Svix | Custom scripts | **Webhook Replay** |
|------------|-----------------|----------------|-------------------|
| Delivery + retry | Yes | DIY | **No (complement)** |
| Byte-identical capture | Partial | Rare | **Yes (WRCAP)** |
| Air-gapped replay proof | No | No | **Yes** |
| Genesis audit export | No | No | **`verify-bundle`** |
| Mesh integration | N/A | DIY | **One env var** |

---

## Architecture

```
Webhook Mesh ingress (optional)
        │
        ▼
┌───────────────────┐
│  CaptureStore     │  .wrcap = header + body bytes
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  ReplayEngine     │  air-gapped, diff SHA256
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  AppendOnlyLedger │  webhook_replay events
└───────────────────┘
```

---

## Integration with Webhook Mesh (#5)

```bash
export WEBHOOK_REPLAY_CAPTURE_DIR=./data/captures
webhook-mesh serve --port 8787
# Every accepted ingress → .wrcap file + existing WAL
```

---

## Institutional proof

| Check | Command |
|-------|---------|
| Unit tests | `pytest tests/test_webhook_replay.py` |
| Rigorous E2E | `scripts/instpp_rigorous_test.sh` |
| Demo | `scripts/demo_webhook_replay.sh` |
| Chaos | Tamper detection in `tests/test_industry_gold.py` |

---

## Explicit non-goals

- Not an event bus or delivery SaaS
- Not a replacement for Webhook Mesh idempotency
- Not real-time streaming analytics
