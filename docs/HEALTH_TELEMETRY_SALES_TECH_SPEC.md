# Health Telemetry Recorder — Sales & Technical Specification

**Product:** Health Telemetry Recorder (#7)  
**SKU:** `health-telemetry`  
**Version:** Institutional++ gold (schema + sequence gate + WAL ingress + observation-lane export)  
**Audience:** Digital health vendors, RPM operators, clinical ops (UK NHS-adjacent), procurement, legal

---

## Executive summary

**One job:** High-frequency **device batches** → schema + sequence validation → Lamport-sealed log → auditor export — **audit spine, not FDA certification**.

**One-line pitch:** *Prove your device telemetry wasn't tampered with — deploy in your VPC, verify offline, no vendor trust required.*

| | |
|---|---|
| **Deploy** | Air-gapped VPC — buyer-operated SQLite + optional HTTP gateway |
| **Proof** | Genesis hash chain + per-device `seq` gate + F7 coverage + `verify-bundle` |
| **Demo** | 60 seconds CLI · `health-telemetry serve` · hospital pilot playbook |

---

## Problem → solution

| Buyer pain | Industry default | Health Telemetry |
|------------|------------------|------------------|
| Cloud vendor trust for integrity | “Trust AWS/Azure” | **Genesis chain — buyer verifies offline** |
| Spreadsheet exports editable | CSV handoff | **Deterministic tar + SHA256 sidecar** |
| Replay / gap attacks on devices | NTP trust only | **Per-device monotonic `seq` gate (fail-closed)** |
| Silent field gaps in vitals | Alert after the fact | **F7 coverage at ingest** |
| PHI in auditor exports | Full payload handoff | **`--observation-lane` export (summaries only)** |
| Gateway crash before ack | Best-effort HTTP 200 | **Ingress WAL fsync before HTTP 200** |
| HIPAA diligence | Vendor SOC cert only | **BAA pack template + VPC deploy** |

---

## Ideal buyer

| Segment | Use case | Why us |
|---------|----------|--------|
| **Digital health / RPM** | Remote patient monitoring batches | Tamper-evident ingest without FDA scope |
| **Clinical ops (NHS-adjacent)** | Ward telemetry integrity | Air-gap + hospital pilot playbook |
| **Compliance / legal** | Dispute evidence for device data | Offline `verify-bundle` |

**Win when:** buyer needs **tamper-evident telemetry log + HIPAA diligence docs**, not a certified medical device.  
**Lose when:** buyer needs FDA/UKCA clearance, EMR/FHIR integration, or real-time clinical alerting UI.

---

## Competitive positioning

| Capability | Cloud IoT hub | Spreadsheet export | **Health Telemetry** |
|------------|---------------|-------------------|---------------------|
| Tamper-evident chain | Vendor trust | None | **Genesis hash chain** |
| Device replay / gap detection | Rare | None | **Per-device `seq` gate** |
| Schema + coverage at ingest | Custom rules | None | **Profile contracts + F7** |
| WAL-before-ack ingress | Vendor trust | N/A | **Separate ingress WAL** |
| PHI-safe auditor export | Redaction service | N/A | **Observation-lane bundle** |
| Offline verify | No | No | **`verify-bundle`** |
| Air-gap deploy | Rare | N/A | **Yes** |
| HIPAA diligence pack | Vendor cert | No | **Docs template + pilot playbook** |

---

## Architecture

```
CLI ingest  OR  POST /v1/telemetry/batch
        │
        ▼
┌───────────────────┐
│  HTTP only:       │  ingress WAL fsync → then process
│  WAL-before-ack   │  (separate *_ingress.wal — not ledger WAL)
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  Schema validate  │  ts + seq + profile fields (rpm_standard: hr, spo2)
│  + F7 coverage    │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  Sequence gate    │  per-device monotonic seq; gap/backward fail-closed
│  (SQLite)         │
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  AppendOnlyLedger │  telemetry_batch + packet_summaries (PHI-light hashes)
└─────────┬─────────┘
          ▼
   check F1–F9 → export [--observation-lane] → verify-bundle
```

Fork of Compliance Logger ingest pattern — same `inst_spine` guarantees.

### Packet contract

Every packet requires **`ts`** (ISO timestamp) and **`seq`** (monotonic integer per device).

| Profile | Required fields beyond ts/seq |
|---------|------------------------------|
| `rpm_standard` (default) | `hr`, `spo2` |
| `vitals_only` | `hr` |
| `minimal` | — |

```json
[
  {"ts": "2026-06-01T12:00:00Z", "seq": 1, "hr": 72, "spo2": 98},
  {"ts": "2026-06-01T12:00:01Z", "seq": 2, "hr": 73, "spo2": 97}
]
```

### HTTP batch ingress

```bash
make health-telemetry-serve
# POST /v1/telemetry/batch
# Body: { "device_id", "packets", "profile?", "batch_id?" }
# Headers: X-Idempotency-Key or X-Batch-Id
```

Receipt is durable in **ingress WAL** before ledger append. Validation failures return **422** with `wal_acked: true` (receipt survived; ingest rejected).

### Drop-in gateway hook

```python
from health_telemetry.integrate import ingest_device_batch

result = ingest_device_batch(
    device_id="ward-7",
    packets=packets,
    ledger_db=Path("data/health_telemetry.sqlite"),
)
```

---

## CLI reference

```bash
pip install -e ".[dev,instpp]"
```

| Command | Purpose |
|---------|---------|
| `health-telemetry ingest --device-id ID --packets JSON [--profile rpm_standard\|vitals_only\|minimal]` | Batch ingest with sequence gate |
| `health-telemetry serve [--host] [--port]` | HTTP WAL-before-ack gateway |
| `health-telemetry check [--database PATH] [--observation-lane]` | F1–F9 institutional check |
| `health-telemetry export [--tarball PATH] [--observation-lane]` | Audit bundle (PHI redacted if observation lane) |
| `health-telemetry verify-bundle --tarball PATH` | Offline auditor replay |

### Environment (HTTP serve)

| Variable | Purpose |
|----------|---------|
| `HEALTH_TELEMETRY_DB` | Ledger SQLite path |
| `HEALTH_TELEMETRY_INGRESS_WAL_PATH` | Ingress receipt WAL (default: `{db_stem}_ingress.wal`) |
| `HEALTH_TELEMETRY_PROFILE` | Default ingest profile |
| `HEALTH_IDEMPOTENCY_TTL_SECONDS` | Duplicate batch TTL |
| `HEALTH_DEVICE_AUTH_SECRET` | When set, `X-Device-Token` HMAC required per `device_id` (production ingress) |
| `HEALTH_TELEMETRY_API_KEY` | When set, `Authorization: Bearer` required on HTTP serve (VPC boundary) |
| `INST_REDIS_URL` | Optional — shared idempotency backend for multi-instance HTTP ingress |

**Merged capability (PR #27, on `main`):** sequence gate + ingress WAL + observation-lane export are shipped in code and rigorous CI — not a roadmap item.

---

## Compliance artifacts

| Document | Purpose |
|----------|---------|
| `docs/HEALTH_TELEMETRY_HIPAA_PACK.md` | BAA diligence template |
| `docs/HEALTH_TELEMETRY_HOSPITAL_PILOT.md` | Ward pilot playbook |
| `docs/SOC2_VPC_DILIGENCE_PACK.md` | VPC deploy SOC mapping |

**Procurement line:** PHI stays in buyer VPC; vendor provides audit spine correctness, not FDA clearance. Signed BAA execution is buyer legal + SOW — not included in license.

---

## Proof & diligence

```bash
./scripts/demo_health_telemetry.sh
make health-telemetry-serve   # optional HTTP path
./scripts/instpp_rigorous_test.sh
health-telemetry verify-bundle --tarball ./health_bundle.tar
```

| Artifact | Path |
|----------|------|
| Rigorous test log | `docs/test_logs/instpp_rigorous_latest.log` |
| Summary | `docs/test_logs/instpp_rigorous_latest_summary.json` |
| Buyer one-pager | `docs/HEALTH_TELEMETRY_BUYER.md` |
| Architecture | `src/health_telemetry/README.md` |

**Industry gold:** HTTP WAL-before-ack, sequence gap fail-closed, observation-lane export — `tests/test_health_telemetry.py` + `tests/test_industry_gold.py`.

---

## Non-goals (say no in RFPs)

- Not FDA / UKCA / DTAC certified medical device software
- Not EMR / HL7 FHIR integration in P1
- Not real-time clinical alerting UI
- Not a cloud IoT device management platform
- Not a signed BAA or ward go-live (templates + pilot SOW only)

---


## RFP quick answers

| Question | Answer |
|----------|--------|
| Tamper-evident device telemetry? | **Yes** — hash chain + export |
| Device sequence / gap detection? | **Yes** — per-device `seq` gate |
| WAL-before-ack HTTP ingress? | **Yes** — `health-telemetry serve` |
| PHI-safe auditor export? | **Yes** — `--observation-lane` |
| Offline third-party verification? | **Yes** — `verify-bundle` |
| Air-gapped VPC deploy? | **Yes** |
| HIPAA BAA diligence support? | **Yes** — template pack (not signed BAA) |
| FDA / DTAC medical device cert? | **No** — audit spine only |
| EMR / FHIR integration? | **No** in P1 |
| Real-time clinical alerts? | **No** |

---

## Related documents

- `docs/HEALTH_TELEMETRY_BUYER.md` — one-page buyer sheet  
- `docs/HEALTH_TELEMETRY_HOSPITAL_PILOT.md` — ward pilot playbook  
- `docs/ROADMAP_GTM_DISCIPLINE.md` — sequence gate ships **inside #7**, not SKU #13
