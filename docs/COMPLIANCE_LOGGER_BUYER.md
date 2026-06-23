# Compliance Logger — Buyer Sheet

**One job:** Tamper-proof audit trail for regulated decisions (approve/deny/escalate) with cryptographic proof an auditor can verify offline.

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|---------------|
| Fintech / payments ops | “Prove what the system decided on date X” | Genesis-anchored hash chain + export bundle |
| Legal / risk / compliance | CSV exports are editable | Deterministic tar + SHA256 sidecar |
| UK sport NGBs / governance | DIAP audit without selling betting UI | Governance infrastructure only |

**Price band:** £300–£800/mo per tenant (infra license; not per-seat GRC).

---

## Tech edge (proof)

| Gate | Evidence |
|------|----------|
| F1–F2 | Snapshot completeness + manifest linkage |
| F3–F4 | Hash chain + Lamport monotonicity (clock-attack resistant) |
| F5 | Config hash stable vs genesis anchor |
| F7 | Source field coverage % on each snapshot |
| F9 | Identical ledger → identical bundle SHA256 |

**Auditor dry-run (no vendor call):**
```bash
compliance-log export --database ./ledger.sqlite
compliance-log verify-bundle --tarball ./audit_bundle.tar
```

---

## 60-second demo

```bash
./scripts/demo_compliance_logger.sh
```

---

## Non-goals

- Not a GRC workflow platform (ServiceNow, Archer)
- Not e-discovery or legal hold UI
- Not bundled with HIBS sports products
- Not a general-purpose SIEM (export feeds SIEM downstream)

---

## CLI

| Command | Purpose |
|---------|---------|
| `ingest` | Log decision snapshot + outcome |
| `check` | Run F1–F9 institutional check |
| `verify-chain` | Hash chain only |
| `export` | Deterministic audit bundle |
| `verify-bundle` | Offline auditor replay |

See `src/compliance_log/README.md` for architecture.  
**Full spec:** `docs/COMPLIANCE_LOGGER_SALES_TECH_SPEC.md`
