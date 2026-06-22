# Inst++ Gold Standard — Compliance Logger & Proxy-Risk Gateway

**Purpose:** What “industry gold standard” means for Inst++ products #1 and #2, and how we prove each dimension.

---

## Six dimensions

| Dimension | What buyers expect | How we prove it |
|-----------|-------------------|-----------------|
| **Correctness** | Fail-closed; no silent drops | All gate outcomes logged; upstream 4xx/5xx → REJECT; Redis backends fail-closed |
| **Failure handling** | Typed errors, no raw tracebacks | `InstError` hierarchy + `run_cli()` JSON envelope |
| **Proof** | Auditor can verify without vendor | Deterministic tar + SHA256; offline `verify-bundle`; F1–F9 report in bundle |
| **Demoability** | One command, repeatable | `demo_compliance_logger.sh`, `demo_proxy_risk.sh`, `instpp_rigorous_test.sh` |
| **Diligence** | Clean package boundaries | Product READMEs, buyer one-pagers, CLI integration tests |
| **Strategic legibility** | One job, clear non-goals | `COMPLIANCE_LOGGER_BUYER.md`, `PROXY_RISK_BUYER.md` |

---

## Quick proof commands

```bash
pip install -e ".[dev,instpp]"
./scripts/instpp_rigorous_test.sh          # full logged E2E
./scripts/demo_compliance_logger.sh        # product #1 buyer demo
./scripts/demo_proxy_risk.sh               # product #2 buyer demo
```

Logs: `docs/test_logs/instpp_rigorous_latest.log`

---

## Correctness guarantees

### Compliance Logger
- Export aborts if genesis/chain/lamport **or** institutional F1–F9 fails
- F7 source coverage computed from snapshot field completeness (not hardcoded 100%)
- Offline `verify-bundle` replays chain without live database

### Proxy-Risk Gateway
- **Every** gate outcome (approve / reject / kill) written to ledger when attached
- Live mode: sync WAL **before** upstream call; upstream failure → REJECT (not approve)
- `INST_CIRCUIT_KILL=1` severs traffic at circuit layer
- Redis token bucket + idempotency: backend outage → reject (fail-closed)

---

## Proof artifacts (per export)

```
MANIFEST.json          — product id, entry count, validation summary
ledger_entries.json    — full hash chain
institutional_check.json — F1–F9 + chain gates
genesis_anchor.json    — offsite-verifiable genesis
wal_full.json          — crash-safe WAL replay
audit_bundle.tar       — deterministic bytes
audit_bundle.tar.sha256.json — cryptographic seal
```

---

## Non-goals (say no in RFPs)

| Product | Not this |
|---------|----------|
| Compliance Logger | GRC workflow UI, e-discovery platform, sports betting |
| Proxy-Risk | Sub-5ms RTB insert, pre-bid DV/IAS, HashiCorp Vault (P1 uses env token adapter) |

---

## Related docs

- `docs/INST_PLUS_DEEP_DIVE_COMPLIANCE_PROXY.md` — industry incumbent map + tech edge (both platforms)
- `docs/COMPLIANCE_LOGGER_BUYER.md` — product #1 sales sheet
- `docs/PROXY_RISK_BUYER.md` — product #2 sales sheet
- `docs/INST_PLUS_TEST_AND_DEMO.md` — command playbook
- `docs/INSTITUTIONAL_ENTERPRISE_STACK.md` — enterprise positioning
