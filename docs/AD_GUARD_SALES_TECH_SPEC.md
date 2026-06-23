# Ad Guard — Sales & Technical Specification

**Product:** Ad Guard (#6)  
**SKU:** `ad-guard`  
**Version:** Gold standard (Google/Meta parsers, NeMo headers, live fail-closed forward)  
**Audience:** Agency ops, growth teams, marketing finance, procurement

---

## Executive summary

**One job:** Guard **marketing API spend** — Z-score kill on anomalous velocity, per-campaign token bucket, and **genesis audit before dollars leave the account**.

**One-line pitch:** *Stop runaway ad API spend at the boundary — with a gate log finance can verify offline.*

| | |
|---|---|
| **Price band** | £300–£800/mo per instance |
| **Deploy** | VPC + Redis (multi-instance) + SQLite spend ledger |
| **Proof** | Every approve/reject/kill on genesis chain + `verify-bundle` |
| **Demo** | 60 seconds CLI · HTTP serve on :8788 |

---

## Problem → solution

| Buyer pain | Industry default | Ad Guard |
|------------|------------------|----------|
| Runaway API spend after misconfig | Post-hoc finance alert | **Z-score kill at API boundary** |
| No proof at spend layer | DSP dashboards | **Genesis chain per gate outcome** |
| Google/Meta payload parsing | Manual field mapping | **Built-in `bidMicros` / `daily_budget` parsers** |
| Upstream errors as success | Optimistic forward | **4xx/5xx → REJECT (fail-closed)** |
| Creative safety vs spend safety | Conflated | **Stack position: NeMo upstream, Ad Guard = spend** |

---

## Stack position

```
GenAI Safety (NeMo/Bedrock) → Ad Guard (spend) → DSP + DV/IAS (placement)
```

Ad Guard is the **spend layer** — not placement verification (DV/IAS) or GenAI safety inference (NeMo).

---

## Ideal buyer

| Segment | Use case | Why us |
|---------|----------|--------|
| **Agency / growth** | Google/Meta API spend guard | Built-in parsers + kill switch |
| **Marketing finance** | Prove spend decisions for disputes | Offline `verify-bundle` |
| **Enterprise marketing** | Layer between safety and DSP | Complements NeMo + DV/IAS |

**Win when:** buyer needs **API-boundary spend kill + audit proof**.  
**Lose when:** buyer needs sub-5ms RTB exchange insert or DV/IAS pre-bid placement.

---

## Competitive positioning

| Capability | Finance alerts | DSP native caps | **Ad Guard** |
|------------|----------------|-----------------|--------------|
| API-boundary kill | Post-hoc | Partial | **Pre-forward Z-score** |
| Google/Meta spend parsers | Manual | N/A | **Built-in** |
| Every gate logged | No | No | **approve/reject/kill** |
| Live upstream fail-closed | N/A | Varies | **4xx/5xx → REJECT** |
| Redis idempotency | No | No | **Same as Proxy-Risk** |
| Offline verify | No | No | **`verify-bundle`** |

---

## Architecture

```
POST spend request
  → circuit → schema → token bucket → idempotency
  → Z-score drift kill
  → optional creative approval headers (NeMo/Bedrock)
  → [shadow | live httpx forward]
  → ledger append → export → verify-bundle
```

### Creative approval gate (optional)

Headers: `X-Nemo-Approved`, `X-Nemo-Safety-Passed`, `X-Bedrock-Guard-Passed`, `X-Creative-Approved`

```bash
export AD_GUARD_REQUIRE_CREATIVE_APPROVAL=1   # fail-closed without approval
```

---

## CLI reference

```bash
pip install -e ".[dev,instpp]"
```

| Command | Purpose |
|---------|---------|
| `ad-guard evaluate --provider google\|meta --body JSON` | Single spend request through gates |
| `ad-guard serve [--port PORT]` | HTTP guard gateway |
| `ad-guard check [--database PATH]` | F1–F9 on spend ledger |
| `ad-guard export [--database PATH] [--tarball PATH]` | Audit bundle |
| `ad-guard verify-bundle --tarball PATH` | Offline auditor replay |

---

## Proof & diligence

```bash
./scripts/demo_ad_guard.sh
./scripts/instpp_rigorous_test.sh
ad-guard verify-bundle --tarball ./ad_guard_bundle.tar
```

| Artifact | Path |
|----------|------|
| Rigorous test log | `docs/test_logs/instpp_rigorous_latest.log` |
| Buyer one-pager | `docs/AD_GUARD_BUYER.md` |
| Stack doc | `docs/AD_GUARD_INSTITUTIONAL_STACK.md` |
| Architecture | `src/ad_guard/README.md` |

---

## Non-goals (say no in RFPs)

- Not DoubleVerify / IAS pre-bid placement verification
- Not sub-5ms RTB exchange insert (Go/Rust territory)
- Not NeMo / Bedrock GenAI safety inference
- Not a DSP or campaign management UI

---

## Pricing & packaging

| Tier | Band | Includes |
|------|------|----------|
| **Instance license** | £300–£800/mo | Gate chain + export + Google/Meta parsers |
| **Multi-instance** | +Redis HA SOW | Fail-closed idempotency across pods |
| **NeMo integration** | Included | Header gate; buyer wires upstream |
| **Maintenance** | 15–20% ARR | Parser updates, spine upgrades |

---

## RFP quick answers

| Question | Answer |
|----------|--------|
| Stop anomalous ad API spend? | **Yes** — Z-score + token bucket |
| Google/Meta payload support? | **Yes** — built-in parsers |
| Every gate decision auditable? | **Yes** — genesis chain + export |
| NeMo creative approval hook? | **Yes** — optional env gate |
| DV/IAS placement verification? | **No** — downstream layer |
| Sub-5ms RTB? | **No** |

---

## Related documents

- `docs/AD_GUARD_BUYER.md` — one-page buyer sheet  
- `docs/AD_GUARD_INSTITUTIONAL_STACK.md` — stack positioning  
- `docs/PORTFOLIO_SALES_SHEET.md` — portfolio pricing matrix
