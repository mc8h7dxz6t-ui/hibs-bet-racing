# Health Telemetry Recorder — Sales & Technical Specification

**Product:** Health Telemetry Recorder (#7)  
**SKU:** `health-telemetry`  
**Version:** Gold standard (batch ingest, Lamport ordering, HIPAA pack, hospital pilot)  
**Audience:** Digital health vendors, RPM operators, clinical ops (UK NHS-adjacent), procurement, legal

---

## Executive summary

**One job:** High-frequency **device batches** → Lamport-ordered sealed log → auditor export — **audit spine, not FDA certification**.

**One-line pitch:** *Prove your device telemetry wasn't tampered with — deploy in your VPC, verify offline, no vendor trust required.*

| | |
|---|---|
| **Price band** | £5k–£15k license + £500/mo maintenance |
| **Deploy** | Air-gapped VPC — buyer-operated SQLite |
| **Proof** | Genesis hash chain + batch Lamport + `verify-bundle` |
| **Demo** | 60 seconds CLI · hospital pilot playbook |

---

## Problem → solution

| Buyer pain | Industry default | Health Telemetry |
|------------|------------------|------------------|
| Cloud vendor trust for integrity | “Trust AWS/Azure” | **Genesis chain — buyer verifies offline** |
| Spreadsheet exports editable | CSV handoff | **Deterministic tar + SHA256 sidecar** |
| Device clock drift | NTP trust | **Lamport ordering per batch** |
| Need tamper evidence, not full EMR | Buy Epic integration | **Audit spine only — fast deploy** |
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
| Clock drift on devices | NTP trust | N/A | **Lamport per batch** |
| Offline verify | No | No | **`verify-bundle`** |
| Air-gap deploy | Rare | N/A | **Yes** |
| HIPAA diligence pack | Vendor cert | No | **Docs template + pilot playbook** |

---

## Architecture

```
POST telemetry_batch
  → schema validate
  → ledger append (device_id + packets)
  → Lamport order per batch
  → F1–F9 check → export → verify-bundle
```

Fork of Compliance Logger ingest pattern — same `inst_spine` guarantees.

---

## CLI reference

```bash
pip install -e ".[dev,instpp]"
```

| Command | Purpose |
|---------|---------|
| `health-telemetry ingest --device-id ID --packets JSON` | Batch telemetry JSON |
| `health-telemetry check [--database PATH]` | F1–F9 institutional check |
| `health-telemetry export [--database PATH] [--tarball PATH]` | Audit bundle |
| `health-telemetry verify-bundle --tarball PATH` | Offline auditor replay |

---

## Compliance artifacts

| Document | Purpose |
|----------|---------|
| `docs/HEALTH_TELEMETRY_HIPAA_PACK.md` | BAA diligence template |
| `docs/HEALTH_TELEMETRY_HOSPITAL_PILOT.md` | Ward pilot playbook |
| `docs/SOC2_VPC_DILIGENCE_PACK.md` | VPC deploy SOC mapping |

**Procurement line:** PHI stays in buyer VPC; vendor provides audit spine correctness, not FDA clearance.

---

## Proof & diligence

```bash
./scripts/demo_health_telemetry.sh
./scripts/instpp_rigorous_test.sh
health-telemetry verify-bundle --tarball ./health_bundle.tar
```

| Artifact | Path |
|----------|------|
| Rigorous test log | `docs/test_logs/instpp_rigorous_latest.log` |
| Buyer one-pager | `docs/HEALTH_TELEMETRY_BUYER.md` |
| Architecture | `src/health_telemetry/README.md` |

---

## Non-goals (say no in RFPs)

- Not FDA / UKCA / DTAC certified medical device software
- Not EMR / HL7 FHIR integration in P1
- Not real-time clinical alerting UI
- Not a cloud IoT device management platform

---

## Pricing & packaging

| Tier | Band | Includes |
|------|------|----------|
| **Site license** | £5k–£15k | CLI + spine + HIPAA pack + export |
| **Maintenance** | £500/mo | Security patches, spine upgrades |
| **Hospital pilot** | £8k–£25k SOW | Ward deploy, BAA review, auditor onboarding |
| **Per-ward expansion** | Custom | Additional ledgers / device namespaces |

---

## RFP quick answers

| Question | Answer |
|----------|--------|
| Tamper-evident device telemetry? | **Yes** — hash chain + export |
| Offline third-party verification? | **Yes** — `verify-bundle` |
| Air-gapped VPC deploy? | **Yes** |
| HIPAA BAA diligence support? | **Yes** — template pack |
| FDA / DTAC medical device cert? | **No** — audit spine only |
| EMR / FHIR integration? | **No** in P1 |
| Real-time clinical alerts? | **No** |

---

## Related documents

- `docs/HEALTH_TELEMETRY_BUYER.md` — one-page buyer sheet  
- `docs/HEALTH_TELEMETRY_HOSPITAL_PILOT.md` — ward pilot playbook  
- `docs/PORTFOLIO_SALES_SHEET.md` — portfolio pricing matrix
