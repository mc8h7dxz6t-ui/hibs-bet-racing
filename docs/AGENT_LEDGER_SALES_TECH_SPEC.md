# Agent Ledger — Sales & Technical Spec (#12)

**SKU:** `agent-ledger` · **Package:** `src/agent_ledger/` · **Spine:** `inst_spine`

---

## One job

Runtime authorization plane for AI agent tool calls — **permit before invoke**, attest after, export offline proof.

---

## Architecture

```
Agent intent (tool + args)
        ↓
   ToolPolicy.evaluate_tool()   ← allowlist, tier ceiling, arg guards
        ↓
   permit | deny | escalate
        ↓
   PermitStore (SQLite WAL)      ← open permit token
        ↓
   inst_spine ledger append      ← authorize event
        ↓
   [ tool executes ]
        ↓
   complete(result) → result_hash on ledger
        ↓
   export → verify-bundle
```

---

## CLI

| Command | Purpose |
|---------|---------|
| `authorize` | Evaluate tool call before execution |
| `complete` | Attest result against open permit |
| `check` | F1–F9 institutional check |
| `export` | Deterministic audit bundle |
| `verify-bundle` | Offline auditor replay |

---

## Policy file (optional)

```json
{
  "agent_tier": "standard",
  "require_human_for_critical": true,
  "allowed_tools": ["read_file", "search_docs", "sql_select"],
  "tool_risk": {
    "read_file": "low",
    "transfer_funds": "critical"
  }
}
```

**Agent tiers:** `sandbox` · `standard` · `privileged` · `break_glass`

---

## Integration

```python
from agent_ledger.integrate import authorize_tool_call, complete_tool_call
```

Pair with **AI Kit** (trace) and **Spend Guard** (costly tools) — orthogonal planes.

---

## Industry Gold checklist

| Dimension | Status |
|-----------|--------|
| Correctness | Fail-closed deny/escalate |
| Proof | export + verify-bundle |
| Demo | `scripts/demo_agent_ledger.sh` |
| Rigorous E2E | `instpp_rigorous_test.sh` |
| Chaos | duplicate complete, idempotent authorize |
| Buyer + spec | This doc + `AGENT_LEDGER_BUYER.md` |

---

## Explicit non-goals

- Not OpenAI tool-calling middleware (integrate at call site)
- Not replacing ModelGovernor lifecycle ledger
