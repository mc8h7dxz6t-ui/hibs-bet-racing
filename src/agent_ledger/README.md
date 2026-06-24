# Agent Ledger (#12)

**One job:** Fail-closed authorization on every AI agent tool call — permit, deny, or escalate — with cryptographic proof an auditor can verify offline.

## vs ModelGovernor (#8)

| | ModelGovernor | Agent Ledger |
|---|---------------|--------------|
| **Governance plane** | Model *artifact* lifecycle | Runtime *tool* invocations |
| **Question answered** | "Who approved model v3.2.1 for prod?" | "Who permitted this SQL write before it ran?" |
| **Buyer** | Model risk / MLOps | Agent platform / security / SOC2 |

## Tech edge

1. **Authorize-before-invoke** — permit token required before tool executes (like Spend Guard reserve-before-dispatch)
2. **Risk-tiered tool taxonomy** — allowlist + agent ceiling + argument guards (SQL injection, path traversal)
3. **Critical-tool escalation** — `human_approved` required or fail-closed
4. **Complete attestation** — result hash chained to permit (intent → permit → result)
5. **Shadow burn-in** — log decisions without blocking
6. **Offline verify-bundle** — same `inst_spine` as all portfolio SKUs

## Quick start

```bash
agent-ledger authorize \
  --agent-id support-bot \
  --tool read_file \
  --args '{"path":"docs/demo_snapshot.json"}' \
  --database data/agent_ledger.sqlite

agent-ledger authorize \
  --agent-id support-bot \
  --tool transfer_funds \
  --args '{"amount":1000}' \
  --database data/agent_ledger.sqlite
# → escalate (critical, no human_approved)

agent-ledger check --database data/agent_ledger.sqlite
agent-ledger export --database data/agent_ledger.sqlite --tarball agent_ledger_bundle.tar
agent-ledger verify-bundle --tarball agent_ledger_bundle.tar
```

## Integration

```python
from agent_ledger.integrate import authorize_tool_call, complete_tool_call

auth = authorize_tool_call(
    agent_id="ops-agent",
    tool_name="sql_select",
    arguments={"query": "SELECT 1"},
    ledger_db=Path("data/agent_ledger.sqlite"),
)
if auth["decision"] != "permit":
    raise PermissionError(auth["reason"])
# ... run tool ...
complete_tool_call(permit_id=auth["permit_id"], result={"rows": 1}, ledger_db=...)
```
