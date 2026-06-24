# Spend Guard — Sales & Technical Specification

**Product:** Spend Guard (Phase 2) — **ModelGovernor 8b CLI**  
**SKU:** `spend-guard`  
**Version:** Industry gold — reserve/settle wallet + drift lockout  
**Audience:** AI platform teams, FinOps, CFO sponsors, procurement, auditors

---

## Executive summary

**One job:** **Reserve** estimated API cost before upstream dispatch, **settle** on actual usage, **lock** wallet when spend drift exceeds rolling threshold — every phase on the **genesis hash chain**.

**One-line pitch:** *Govern money, not just traffic — reserve before dispatch.*

| | |
|---|---|
| **Price band** | £2,500–£5,000/mo per tenant |
| **Semantics** | Reserve → dispatch → settle (two-phase commit) |
| **Drift lockout** | `DRIFT_THRESHOLD_EXCEEDED` → 409 on next reserve |
| **Proof** | `spend_guard` events + offline `verify-bundle` |

---

## Problem → solution

| Buyer pain | Industry default | Spend Guard |
|------------|------------------|-------------|
| Weekend API bill spike | Alerts after spend | **Reserve holds budget** |
| Retry double-charges | Best-effort idempotency | **`request_id` unique holds** |
| LiteLLM budgets | Tracking limits | **Ledger settlement semantics** |
| Audit "who spent what" | Cloud console | **Genesis chain per reserve/settle** |

---

## Competitive positioning

| Capability | LiteLLM budgets | Portkey | Helicone | **Spend Guard** |
|------------|-----------------|---------|----------|-----------------|
| Route models | Yes | Yes | Observe | **No (pairs)** |
| Reserve before call | No | Partial | No | **Yes** |
| Drift wallet lockout | No | No | No | **Yes** |
| Offline audit proof | No | No | No | **`verify-bundle`** |
| Air-gap VPC | Rare | SaaS | SaaS | **Default** |

---

## Architecture

```
API call request
        │
        ▼
┌───────────────────┐
│  reserve(cost)    │  SQLite BEGIN IMMEDIATE
└─────────┬─────────┘
          ▼
    [ upstream dispatch ]
          ▼
┌───────────────────┐
│  settle(actual)   │  debit balance, drift check
└─────────┬─────────┘
          ▼
┌───────────────────┐
│  AppendOnlyLedger │  spend_guard events
└───────────────────┘
```

### Drift lockout

When a settle amount exceeds `rolling_avg × (1 + threshold)`, wallet locks. Next reserve returns **locked** — fail-closed.

---

## Integration

```python
from spend_guard.integrate import reserve_api_call, settle_api_call

r = reserve_api_call(request_id="req-1", estimated_cost=0.05, wallet_db=Path("wallet.sqlite"))
# ... upstream LLM ...
settle_api_call(hold_id=r["hold_id"], actual_cost=0.04, request_id="req-1", wallet_db=Path("wallet.sqlite"))
```

---

## ModelGovernor 8b relationship

| Layer | SKU | Status |
|-------|-----|--------|
| Lifecycle governance CLI | ModelGovernor 8a | Rigorous E2E ✅ |
| **Spend plane CLI** | **Spend Guard** | Rigorous E2E ✅ |
| Postgres compose demo | `make demo-gold` | Documented north star — not in rigorous CI |

**Sales honesty:** Lead with Spend Guard CLI + `verify-bundle`. Mention `make demo-gold` as strategic north star when compose stack is in buyer environment.

---

## Institutional proof

| Check | Command |
|-------|---------|
| Unit tests | `pytest tests/test_spend_guard.py` |
| Rigorous E2E | `scripts/instpp_rigorous_test.sh` |
| Demo | `scripts/demo_spend_guard.sh` |
| Chaos | Duplicate request_id, insufficient balance |

---

## Explicit non-goals

- Not OpenAI-compatible gateway (integrate at call site)
- Not Postgres multi-region wallet (SOW)
- Not invoice / ERP integration
