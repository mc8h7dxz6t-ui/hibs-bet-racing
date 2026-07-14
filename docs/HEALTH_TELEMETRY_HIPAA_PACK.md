# Health Telemetry — HIPAA Diligence Pack (Template)

**Purpose:** Buyer-facing diligence template for BAA conversations. This product provides **tamper-evident audit infrastructure** — not HIPAA certification, FDA clearance, or a covered-entity BAA by itself.

**Product:** Health Telemetry Recorder (`health_telemetry`)  
**Standard:** Institutional gold standard — genesis WAL, F1–F9 gates, offline `verify-bundle`

---

## 1. Scope boundary

| In scope | Out of scope |
|----------|--------------|
| Append-only telemetry batch ledger | PHI de-identification pipeline |
| Cryptographic chain + export bundle | EMR / FHIR write-back |
| Air-gap VPC deployment option | SOC 2 Type II attestation (buyer VPC) |
| Access control via deployment IAM | Clinical decision support |

---

## 2. PHI handling (deployment model)

**Default posture:** Deploy in buyer-controlled VPC. Telemetry payloads are **buyer-defined JSON** — the recorder does not classify PHI.

| Control | Implementation |
|---------|----------------|
| Encryption at rest | Buyer disk / volume encryption (EBS, LUKS) |
| Encryption in transit | TLS termination at buyer ingress |
| Access logging | Buyer IAM + optional forward of ledger export to SIEM |
| Minimum necessary | Batch schema defined by buyer integration contract |
| Retention | Buyer policy; ledger supports export + archival tar |

---

## 3. Audit trail evidence

```bash
health-telemetry ingest --device-id <device> --packets '<json array>' --database ./ledger.sqlite
health-telemetry check --database ./ledger.sqlite
health-telemetry export --database ./ledger.sqlite --tarball ./audit_bundle.tar
health-telemetry verify-bundle --tarball ./audit_bundle.tar
```

**F-gates applied:** F1 snapshot completeness · F3 hash chain · F4 Lamport · F9 deterministic export.

---

## 4. BAA checklist (buyer + vendor)

- [ ] Business Associate Agreement executed (if vendor hosts PHI)
- [ ] Data flow diagram signed (device → ingress → ledger → export)
- [ ] Breach notification process documented
- [ ] Subprocessor list (cloud provider, Redis if used)
- [ ] Workforce access policy for ledger databases
- [ ] Disaster recovery: genesis anchor offsite copy
- [ ] Penetration test scope includes ingress endpoint

---

## 5. Incident response hooks

| Event | Recorder behavior |
|-------|-------------------|
| Ledger tamper attempt | `verify-chain` / `verify-bundle` fails closed |
| Ingress flood | Rate limit at buyer WAF (not in P1 product) |
| Device clock skew | Lamport ordering preserves causal batch order |

---

## 6. Honest limitations

- No built-in de-identification or tokenization
- No 42 CFR Part 2 specialty controls
- Enterprise sales cycle typically 6–12 months with clinical stakeholders
- Extreme volume batching may need tuning (math unchanged)

---

## Related

- `docs/HEALTH_TELEMETRY_BUYER.md` — sales one-pager
- `src/health_telemetry/README.md` — architecture
- `docs/INSTITUTIONAL_STANDARD.md` — portfolio gold standard
