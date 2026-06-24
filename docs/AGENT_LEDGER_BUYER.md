# Agent Ledger — Buyer Sheet (#12)

**One job:** Fail-closed runtime governance for AI agent tool calls — prove which actions were permitted, denied, or escalated *before* execution.

**Pitch:** *ModelGovernor proves which model was approved. Agent Ledger proves which tools actually ran — with math, not agent logs.*

---

## vs ModelGovernor (#8)

| ModelGovernor | Agent Ledger |
|---------------|--------------|
| Model artifact lifecycle (register/approve/deploy) | Runtime tool authorization (permit/deny/escalate) |
| SR 11-7 / model risk evidence | SOC2 / agent security / platform governance |
| "Who signed off model v3.2.1?" | "Who permitted this funds transfer before the agent ran it?" |

**Sell together:** lifecycle governance + runtime action proof.

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| Agent platform teams | Tool calls are invisible in prod | Authorize-before-invoke + hash-chained ledger |
| Security / GRC | No proof of agent guardrails | Offline `verify-bundle` |
| Fintech / ops agents | Critical tools need human gate | Escalation lane + `human_approved` attestation |
| Compliance | Conflated with generic LLM safety | Tool-specific policy + argument guards |

**Price band:** £500–£1,500/mo per agent fleet (policy + ledger + export).

---

## Tech edge

| Edge | Evidence |
|------|----------|
| Authorize → complete chain | Permit store + result hash on ledger |
| Risk-tiered tool taxonomy | low → critical with agent ceiling |
| Argument guards | SQL injection, path traversal fail-closed |
| Shadow burn-in | Log without blocking (Proxy-Risk pattern) |
| Offline verify-bundle | Auditor never calls your agent runtime |

```bash
./scripts/demo_agent_ledger.sh
agent-ledger verify-bundle --tarball ./data/demo/agent_ledger_bundle.tar
```

---

## Non-goals

- Not a full agent framework (LangChain, AutoGPT, CrewAI)
- Not model lifecycle registry (see ModelGovernor)
- Not LLM spend metering (see Spend Guard)
- Not prompt safety / content moderation (see Ad Guard / AI Kit)

---

## Related

- [AGENT_LEDGER_SALES_TECH_SPEC.md](AGENT_LEDGER_SALES_TECH_SPEC.md)
- [MODEL_GOVERNOR_BUYER.md](MODEL_GOVERNOR_BUYER.md) — complementary #8 SKU
