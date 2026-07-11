# Ad Guard — Buyer Sheet

**One job:** Guard marketing API spend — Z-score kill on anomalous velocity, per-campaign bucket, genesis audit before dollars leave the account.

**Pitch:** *Stop runaway ad API spend at the boundary — with a gate log finance can verify offline.*

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| Agency / growth teams | Runaway API spend after misconfiguration | Token bucket + Z-score kill + full gate log |
| Finance / compliance | Post-hoc alerts, no API-boundary proof | Every approve/reject/kill on genesis chain |
| Enterprise marketing stack | DV/IAS guard placement, not spend | Spend layer between NeMo and DSP |


---

## Stack position

```
GenAI Safety (NeMo/Bedrock) → Ad Guard (spend) → DSP + DV/IAS (placement)
```

---

## Tech edge (proof)

| Gate | Evidence |
|------|----------|
| Spend parsers | Google `bidMicros` / Meta `daily_budget` built-in |
| Z-score kill | Per-campaign drift detector |
| Idempotency | Redis fail-closed (multi-instance) |
| Live mode | WAL before upstream; 4xx/5xx → REJECT |
| Creative hook | `X-Creative-Approved` header (optional env gate) |

**Auditor dry-run:**
```bash
ad-guard evaluate --provider google --body '{"campaignId":"12345","bidMicros":2500000}'
ad-guard export --database ./ad_guard.sqlite --tarball ./ad_guard_bundle.tar
ad-guard verify-bundle --tarball ./ad_guard_bundle.tar
```

---

## 60-second demo

```bash
./scripts/demo_ad_guard.sh
ad-guard serve --port 8788
```

---

## Non-goals

- Not DoubleVerify / IAS pre-bid placement verification
- Not sub-5ms RTB exchange insert
- Not NeMo / Bedrock GenAI safety inference

---

## CLI

| Command | Purpose |
|---------|---------|
| `evaluate` | Single spend request through gate chain |
| `serve` | HTTP guard gateway |
| `check` | F1–F9 on spend ledger |
| `export` | Audit bundle |
| `verify-bundle` | Offline auditor replay |

See `src/ad_guard/README.md` for architecture.  
**Full spec:** `docs/AD_GUARD_SALES_TECH_SPEC.md`

---

## Next step

| Step | Action |
|------|--------|
| 1 | `./scripts/demo_ad_guard.sh` (60s) |
| 2 | `ad-guard verify-bundle --tarball ./ad_guard_bundle.tar` |
| 3 | RFP depth → `docs/AD_GUARD_SALES_TECH_SPEC.md` |
