# Health Telemetry Recorder — Buyer Sheet

**One job:** High-frequency device batches → Lamport-ordered sealed log → auditor export — **audit spine, not FDA certification**.

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| Digital health / RPM vendors | Cloud vendor trust for telemetry integrity | Genesis hash chain + offline `verify-bundle` |
| Clinical ops (UK NHS adjacent) | Spreadsheet exports are editable | Deterministic tar + SHA256 sidecar |
| Compliance / legal | Need tamper evidence, not full EMR | Air-gap VPC deploy + HIPAA pack template |

**Price band:** £5k–£15k license + £500/mo maintenance.

---

## Tech edge (proof)

| Capability | Evidence |
|------------|----------|
| Batch ingest | Schema-validated `telemetry_batch` events |
| Clock drift | Lamport ordering per device batch |
| F1–F9 | Same institutional gates as portfolio spine |
| HIPAA diligence | `docs/HEALTH_TELEMETRY_HIPAA_PACK.md` template |

**Auditor dry-run:**
```bash
health-telemetry ingest --device-id ward-7 --packets '[{"hr":72}]'
health-telemetry export --database ./health.sqlite --tarball ./health_bundle.tar
health-telemetry verify-bundle --tarball ./health_bundle.tar
```

---

## 60-second demo

```bash
./scripts/demo_health_telemetry.sh
```

---

## Non-goals

- Not FDA / UKCA / DTAC certified medical device software
- Not EMR / HL7 FHIR integration in P1
- Not real-time clinical alerting UI

---

## CLI

| Command | Purpose |
|---------|---------|
| `ingest` | Batch telemetry JSON |
| `check` | F1–F9 institutional check |
| `export` | Audit bundle |
| `verify-bundle` | Offline auditor replay |

See `src/health_telemetry/README.md` and `docs/HEALTH_TELEMETRY_HIPAA_PACK.md`.
