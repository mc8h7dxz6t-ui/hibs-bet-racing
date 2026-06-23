# Compliance Logger — Sales & Technical Specification

**Product:** Compliance Logger (#1)  
**SKU:** `compliance-log`  
**Version:** Gold standard (full institutional test suite, offline verify-bundle, workflow UI)  
**Audience:** Legal, risk, governance, procurement, auditors, enterprise architects

---

## Executive summary

**One job:** Record every regulated decision (approve / deny / escalate) with an **input snapshot**, **outcome**, and **tamper-evident cryptographic chain** that a third party can verify **offline — without calling the vendor**.

**One-line pitch:** *Prove what your systems decided and when — with math, not slides.*

| | |
|---|---|
| **Price band** | £300–£800/mo per tenant (infra license) |
| **Deploy** | Air-gapped VPC / on-prem — SQLite + WAL |
| **Proof** | Genesis-anchored hash chain + deterministic audit tarball |
| **Demo** | 60 seconds CLI · browser workflow console |

---

## Problem → solution

| Buyer pain | Industry default | Compliance Logger |
|------------|------------------|-------------------|
| “Prove decision on date X” | CSV/PDF export (editable) | Snapshot + outcome + hash chain |
| Auditor distrust | “Trust our dashboard” | Offline `verify-bundle` on tarball only |
| Clock spoofing | Wall-clock timestamps | Lamport logical clocks (F4) |
| Vendor lock-in | SaaS-only export | Air-gap deploy; buyer holds ledger |
| Reproducibility disputes | Non-deterministic exports | F9 — identical ledger → identical bundle SHA256 |

---

## Ideal buyer

| Segment | Use case | Why us |
|---------|----------|--------|
| **Fintech / payments** | KYC/AML approval trails | Decision snapshot is first-class |
| **Legal / risk** | Model governance, policy exceptions | Tamper-evident chain beats spreadsheet |
| **UK sport NGBs** | DIAP / governance evidence | Infrastructure only — no betting UI |
| **Insurtech / lending** | Underwriting decision audit | Offline auditor replay for disputes |

**Win when:** buyer needs **proof**, not GRC case management.  
**Lose when:** buyer needs ServiceNow-style workflow, SOC 2 certified multi-tenant SaaS out of the box.

---

## Competitive positioning

| Capability | GRC SaaS (Archer, ServiceNow) | immudb / QLDB class | **Compliance Logger** |
|------------|--------------------------------|---------------------|----------------------|
| Decision snapshot + outcome | Custom fields | BYO schema | **First-class ingest contract** |
| Tamper detection | RBAC | Merkle / immutability | **Sequential hash chain + genesis anchor** |
| Clock-attack resistance | Weak | Varies | **Lamport monotonic (F4)** |
| Offline auditor replay | No | Partial (needs DB) | **`verify-bundle` tarball only** |
| Deterministic export hash | No | No | **F9 reproducibility gate** |
| Workflow UI | Strong | None | **Guided 5-step proof console** |
| Air-gap | Rare | Yes | **Default architecture** |

---

## Architecture

```
Business application
        │
        ▼
┌───────────────────┐
│  ingest           │  snapshot JSON + outcome JSON + actor
│  (compliance_log) │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  SYNC: WAL fsync  │  survives crash before SQLite flush
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  AppendOnlyLedger │  genesis block 0 + hash chain + Lamport seq
│  (inst_spine)     │
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  check F1–F9      │  institutional gate matrix
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  export           │  deterministic tar + SHA256 sidecar
└─────────┬─────────┘
          │
          ▼
┌───────────────────┐
│  verify-bundle    │  auditor dry-run (no live DB)
└───────────────────┘
```

### Durability model

1. **Hot write:** WAL append with `fsync` before ACK  
2. **Index:** SQLite for query/export (async optional)  
3. **Genesis:** Block 0 bound to offsite anchor file  
4. **Export abort:** Bundle build fails if chain or F1–F9 fails  

### Package layout (standalone extract)

```
compliance-logger/
├── src/compliance_log/     # ingest + CLI (3 modules)
├── src/inst_spine/         # shared audit spine (required)
├── docs/demo_snapshot.json
├── scripts/demo_compliance_logger.sh
└── pyproject.toml          # compliance-log entry point
```

**Zero dependency** on `proxy_risk`, sports, or racing code.

---

## Institutional gates (F1–F9)

| Gate | Evidence |
|------|----------|
| **ledger_chain** | Sequential hash integrity |
| **genesis_block** | Installation origin matches anchor |
| **lamport_order** | Logical clock strictly increasing |
| **F1** | Snapshot completeness vs expected count |
| **F2** | Manifest linkage on non-genesis entries |
| **F3** | Hash chain verification |
| **F4** | Lamport monotonicity |
| **F5** | Config hash stable vs genesis anchor |
| **F6** | Entry count reconciliation |
| **F7** | Source field coverage % on snapshots |
| **F8** | Retention policy compliance |
| **F9** | Identical ledger → identical bundle SHA256 |

---

## CLI reference

```bash
pip install -e ".[dev,instpp]"
```

| Command | Purpose |
|---------|---------|
| `compliance-log ingest --snapshot <json> [--outcome <json>] [--actor NAME] [--database PATH]` | Log one decision |
| `compliance-log check [--database PATH] [--observation-lane]` | Run F1–F9 institutional check |
| `compliance-log verify-chain [--database PATH]` | Hash chain only |
| `compliance-log export [--database PATH] [--tarball PATH] [--repro-check]` | Deterministic audit bundle |
| `compliance-log verify-bundle --tarball PATH [--anchor PATH]` | Offline auditor replay |

### Ingest contract

```json
{
  "snapshot": {
    "action": "approve",
    "amount": 1000,
    "currency": "GBP",
    "customer_id": "cust_001",
    "policy": "kyc_tier_2",
    "risk_score": 0.12
  },
  "outcome": {
    "status": "approved",
    "ref": "case-2026-001"
  }
}
```

---

## Workflow UI (single-product console)

```bash
# After demo or with your ledger:
inst-workflow serve --product compliance --port 8790
# → http://127.0.0.1:8790
```

5-step guided workflow: **Ingest → Chain → F1–F9 → Export → Verify offline**

Env alternative: `INST_WORKFLOW_PRODUCT=compliance`

---

## Export artifacts (per bundle)

| File | Contents |
|------|----------|
| `MANIFEST.json` | Product id, entry count, validation summary |
| `ledger_entries.json` | Full hash chain |
| `institutional_check.json` | F1–F9 + chain gates |
| `genesis_anchor.json` | Offsite-verifiable genesis |
| `wal_full.json` | Crash-safe WAL replay |
| `audit_bundle.tar` | Deterministic bytes |
| `audit_bundle.tar.sha256.json` | Cryptographic seal |

---

## Security & deployment

| Concern | Approach |
|---------|----------|
| **Data residency** | All data local — no vendor cloud required |
| **Tampering** | Hash chain breaks on any edit |
| **Crash safety** | WAL fsync before index |
| **Multi-tenant** | Separate SQLite per tenant (buyer-operated) |
| **Auth** | CLI/VPC boundary — HTTP serve optional |

### Reference deploy

- **Single tenant:** one VM, one SQLite file, nightly export to cold storage  
- **Audit cadence:** export → `verify-bundle` → hand tarball to auditor  
- **SIEM downstream:** export JSON feeds Splunk/Datadog (not a SIEM replacement)

---

## Proof & diligence

```bash
./scripts/demo_compliance_logger.sh
./scripts/instpp_rigorous_test.sh    # logged E2E → docs/test_logs/
compliance-log verify-bundle --tarball data/demo/compliance_bundle.tar
```

| Artifact | Path |
|----------|------|
| Rigorous test log | `docs/test_logs/instpp_rigorous_latest.log` |
| Buyer one-pager | `docs/COMPLIANCE_LOGGER_BUYER.md` |
| Deep dive | `docs/INST_PLUS_DEEP_DIVE_COMPLIANCE_PROXY.md` |
| Architecture | `src/compliance_log/README.md` |

---

## Non-goals (say no in RFPs)

- Not a GRC workflow platform (ServiceNow GRC, Archer, MetricStream)
- Not e-discovery or legal hold UI
- Not a general-purpose SIEM
- Not bundled with HIBS sports products
- Not blockchain theatre — proof without nodes

---

## Pricing & packaging

| Tier | Band | Includes |
|------|------|----------|
| **Tenant license** | £300–£800/mo | CLI + spine + export + verify-bundle |
| **Workflow console** | Included | `inst-workflow serve --product compliance` |
| **Implementation** | Custom SOW | Schema mapping, anchor ceremony, auditor onboarding |
| **Maintenance** | 15–20% ARR | Security patches, spine upgrades |

**Sell separately** from Proxy-Risk — different buyer, different diligence thread.

---

## RFP quick answers

| Question | Answer |
|----------|--------|
| Tamper-proof decision audit trail? | **Yes** |
| Offline third-party verification? | **Yes** — `verify-bundle` |
| Air-gapped deploy? | **Yes** |
| Prove model approval on date X? | **Yes** — snapshot + outcome + export |
| GRC case management UI? | **No** — integrate export into GRC |
| SOC 2 Type II certified SaaS? | **Not yet** — buyer VPC deploy |

---

## Related documents

- `docs/COMPLIANCE_LOGGER_BUYER.md` — one-page buyer sheet  
- `docs/PORTFOLIO_SALES_SHEET.md` — portfolio pricing matrix  
- `docs/BUYER_EVIDENCE_PACK.md` — procurement dry-run  
- `docs/INST_PLUS_PRE_REV_VALUATION.md` — IP valuation framework  
- `docs/DEMO.md` — demo commands
