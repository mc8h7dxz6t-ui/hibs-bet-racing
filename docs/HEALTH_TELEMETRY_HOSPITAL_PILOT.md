# Health Telemetry — Hospital Pilot Playbook

**Purpose:** Guide NHS-adjacent and digital-health buyers through a **ward-scale pilot** using the Health Telemetry Recorder.  
**Sales cycle:** Typically multi-stakeholder (clinical, IG, procurement) — plan for structured phases, not a single demo.

**Companion:** `docs/HEALTH_TELEMETRY_HIPAA_PACK.md` (US BAA template) · UK: DPIA + DPA with NHS trust IG.

---

## 1. Pilot scope (recommended)

| Phase | Devices | Duration | Success metric |
|-------|---------|----------|----------------|
| **Lab** | 1 simulator | 1 week | `verify-bundle` passes; IG review |
| **Ward** | 5–20 beds | 4–8 weeks | Zero chain failures; export accepted by IG |
| **Scale** | 100+ beds | Post-pilot | Throughput tuning; EMR integration RFP |

**In scope:** Tamper-evident batch ingest, Lamport ordering, offline audit export.  
**Out of scope:** Clinical alerting UI, FDA/UKCA, FHIR write-back (separate integration SOW).

---

## 2. Technical setup

```bash
./scripts/demo_health_telemetry.sh
health-telemetry ingest --device-id ward-7 --packets '[{"hr":72,"spo2":98}]'
health-telemetry check --database ./health.sqlite
health-telemetry export --database ./health.sqlite --tarball ./ward7_audit.tar
health-telemetry verify-bundle --tarball ./ward7_audit.tar
```

**Deploy:** Buyer VPC (see `docs/SOC2_VPC_DILIGENCE_PACK.md`).

| Env | Purpose |
|-----|---------|
| `HEALTH_TELEMETRY_DATABASE` | Ledger path on encrypted volume |
| Ingress TLS | Trust-managed cert at API gateway |
| Batch schema | Signed JSON contract per device type |

---

## 3. Stakeholder map

| Role | Cares about | Demo hook |
|------|-------------|-----------|
| Clinical engineering | Data integrity | Lamport batch order |
| Information governance | Tamper evidence | `verify-bundle` without vendor |
| Procurement | Liability boundary | HIPAA/DPIA pack + non-cert disclaimer |
| CISO | SOC 2 | VPC diligence pack |

---

## 4. Pilot deliverables

1. Signed data-flow diagram (device → ingress → ledger → export)
2. Weekly `check` + monthly `export` tarball to IG share
3. Genesis anchor offsite copy procedure
4. Incident drill: deliberate tamper → `verify-bundle` fails closed

---

## 5. Pilot framing

| Item | Notes |
|------|-------|
| Pilot | Ward deploy, 8 weeks — procurement offline |
| Production | VPC license + maintenance — procurement offline |
| Integration SOW | FHIR/EMR quoted separately |

---

## 6. Exit criteria → production

- [ ] IG sign-off on export format
- [ ] 30 days continuous ingest without chain failure
- [ ] DPIA / BAA executed (if PHI in scope)
- [ ] Runbook for device onboarding + key rotation
- [ ] SOC 2 / ISO scope assigned to buyer ops (see VPC pack)

**Buyer sheet:** `docs/HEALTH_TELEMETRY_BUYER.md`
