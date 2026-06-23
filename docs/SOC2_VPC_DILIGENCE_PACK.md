# SOC 2 Type II — VPC Deploy Diligence Pack (All Products)

**Purpose:** Shared security diligence template for enterprise buyers.  
**Posture:** We sell **audit infrastructure** deployed in **buyer-controlled VPC** — SOC 2 Type II attestation is a **buyer or shared-processor** responsibility, not a product SKU.

**Applies to:** All 7 portfolio products on `inst_spine`.

---

## 1. Trust model

| Layer | Owner | Notes |
|-------|-------|-------|
| Application code | Vendor | Genesis WAL, F-gates, deterministic export |
| Runtime / network | **Buyer VPC** | IAM, TLS, WAF, secrets manager |
| SOC 2 Type II report | **Buyer or MSP** | Vendor provides evidence artifacts, not certification |
| PHI / regulated data | **Buyer** | Payload schema + BAA (see Health Telemetry pack) |

**One-line for procurement:** *Deploy our tarball in your VPC; your SOC 2 scope covers ops; our scope is provable correctness of the audit spine.*

---

## 2. Control mapping (CC series — illustrative)

| SOC 2 criteria | Institutional product evidence |
|----------------|------------------------------|
| CC6.1 Logical access | Buyer IAM; no vendor SaaS login required |
| CC6.6 Encryption | TLS at ingress; buyer disk encryption at rest |
| CC7.2 Monitoring | Ledger `check` + export to buyer SIEM |
| CC7.3 Change detection | Hash chain + `verify-bundle` offline |
| CC8.1 Change management | Deterministic F9 export; git-tagged releases |
| CC9.2 Vendor risk | Air-gap option; no mandatory vendor callback |

---

## 3. Evidence pack (per product)

```bash
pip install -e ".[dev,instpp]"
./scripts/instpp_smoke_test.sh
./scripts/instpp_rigorous_test.sh
./scripts/demo_<product>.sh
<product> export --database ./ledger.sqlite --tarball ./audit_bundle.tar
<product> verify-bundle --tarball ./audit_bundle.tar
```

Commit or attach: `docs/test_logs/instpp_rigorous_latest_summary.json`

---

## 4. VPC reference architecture

```
[Internet] → [Buyer WAF/API GW] → [Product pod — Compliance / Proxy / Webhook / …]
                                      ↓
                              [AppendOnlyLedger sqlite + WAL]
                                      ↓
                              [Scheduled export → S3/Glacier]
                                      ↓
                              [Auditor verify-bundle offline]
```

| Component | Recommendation |
|-----------|----------------|
| Secrets | AWS Secrets Manager / HashiCorp Vault |
| Redis (optional) | ElastiCache — idempotency + token bucket |
| Ledger backup | Cross-region genesis anchor copy |
| Logs | Forward stdout + export bundles to SIEM |

---

## 5. Questionnaire deflection

| Buyer asks | Answer |
|------------|--------|
| SOC 2 Type II certified SaaS? | **No** — VPC deploy; buyer controls ops scope |
| Pen test report? | Buyer runs against their deployment; we provide test suite |
| Data residency? | **Buyer region** — no vendor cloud required |
| Subprocessors? | Optional: buyer cloud provider only |

---

## 6. Type I readiness (vendor-side, optional)

- [ ] Architecture diagram signed per product
- [ ] `instpp_rigorous_test.sh` log in data room
- [ ] Incident response runbook (buyer executes)
- [ ] SBOM / dependency scan in CI
- [ ] Change log per release tag

**Related:** `docs/HEALTH_TELEMETRY_HIPAA_PACK.md` (PHI-specific), `docs/INSTITUTIONAL_STANDARD.md`
