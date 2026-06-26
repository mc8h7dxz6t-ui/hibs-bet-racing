# Health Telemetry Recorder — Buyer Sheet

**One job:** Device batches → schema + sequence gate → Lamport-sealed log → auditor export — **audit spine, not FDA certification**.

**Pitch:** *Prove your device telemetry wasn't tampered with — deploy in your VPC, verify offline.*

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| Digital health / RPM vendors | Cloud vendor trust for telemetry integrity | Genesis hash chain + offline `verify-bundle` |
| Clinical ops (UK NHS adjacent) | Spreadsheet exports are editable | Deterministic tar + SHA256 sidecar |
| Compliance / legal | Replay/gap attacks on device streams | **Per-device `seq` gate (fail-closed)** |
| Security / privacy | PHI in audit exports | **`--observation-lane`** — summaries only |

**Price band:** £5k–£15k license + £500/mo maintenance · **£12k–£14k sale-now** perpetual VPC.

---

## Tech edge (proof)

| Capability | Evidence |
|------------|----------|
| Schema + F7 coverage | `ts`, `seq`, profile fields at ingest |
| Sequence gate | Gap/backward `seq` rejected per `device_id` |
| HTTP ingress | WAL fsync before ack — `health-telemetry serve` |
| PHI-light export | `packet_summaries` + observation-lane redaction |
| F1–F9 | Same institutional gates as portfolio spine |
| HIPAA diligence | `docs/HEALTH_TELEMETRY_HIPAA_PACK.md` template |

**Auditor dry-run:**
```bash
health-telemetry ingest --device-id ward-7 \
  --packets '[{"ts":"2026-06-01T12:00:00Z","seq":1,"hr":72,"spo2":98}]'
health-telemetry export --database ./health.sqlite --tarball ./health_bundle.tar
health-telemetry verify-bundle --tarball ./health_bundle.tar
```

**PHI-safe export:**
```bash
health-telemetry export --observation-lane --tarball ./health_obs.tar
```

---

## 60-second demo

```bash
./scripts/demo_health_telemetry.sh
make health-telemetry-serve   # optional HTTP batch ingress
```

---

## Non-goals

- Not FDA / UKCA / DTAC certified medical device software
- Not EMR / HL7 FHIR integration in P1
- Not real-time clinical alerting UI
- Not signed BAA (template + pilot SOW only)

---

## CLI

| Command | Purpose |
|---------|---------|
| `ingest` | Batch telemetry JSON (`seq` required) |
| `serve` | HTTP `POST /v1/telemetry/batch` |
| `check` | F1–F9 institutional check |
| `export` | Audit bundle (`--observation-lane` for PHI-safe) |
| `verify-bundle` | Offline auditor replay |

See `src/health_telemetry/README.md` and `docs/HEALTH_TELEMETRY_HIPAA_PACK.md`.  
**Full spec:** `docs/HEALTH_TELEMETRY_SALES_TECH_SPEC.md`

---

## Next step

| Step | Action |
|------|--------|
| 1 | `./scripts/demo_health_telemetry.sh` (60s) |
| 2 | `health-telemetry verify-bundle --tarball ./health_bundle.tar` |
| 3 | RFP depth → `docs/HEALTH_TELEMETRY_SALES_TECH_SPEC.md` |
| 4 | Hospital pilot → `docs/HEALTH_TELEMETRY_HOSPITAL_PILOT.md` |
