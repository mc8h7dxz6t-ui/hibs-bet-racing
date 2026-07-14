# AI Kit — Sales & Technical Specification

**Product:** AI Kit (#4)  
**SKU:** `ai-kit`  
**Version:** Gold standard (live LLM optional, Lamport checkpoints, trace export)  
**Audience:** Platform engineering, ML/AI teams, compliance reviewers, procurement

---

## Executive summary

**One job:** Ship **agentic AI features** without rate-limit explosions, lost state on worker crash, or unvalidated JSON blobs — with a **tamper-evident trace ledger**.

**One-line pitch:** *Run agents in production with checkpoints, rate limits, and an audit trail auditors can verify offline.*

| | |
|---|---|
| **Deploy** | Air-gapped VPC — SQLite trace ledger |
| **Proof** | Lamport checkpoints + trace export + `verify-bundle` |
| **Demo** | 60 seconds CLI · `--live-llm` optional |

---

## Problem → solution

| Buyer pain | Industry default | AI Kit |
|------------|------------------|--------|
| Rate limits crash production | Raw exceptions | **Token bucket + typed `RateLimitError`** |
| Lost state on worker crash | Restart from scratch | **Lamport checkpoints + resume** |
| “What did the agent do?” | Unstructured logs | **AppendOnlyLedger trace + export** |
| Invalid JSON from LLM | Manual retry loops | **`validate_with_retry` wired in CLI** |
| No audit for agent decisions | SaaS dashboard trust | **Offline `verify-bundle` on trace** |

---

## Ideal buyer

| Segment | Use case | Why us |
|---------|----------|--------|
| **Platform teams** | Add agents to existing product | Rate limits + checkpoints without framework lock-in |
| **ML / AI engineers** | Multi-step agent workflows | Resume from Lamport checkpoint after crash |
| **Compliance / risk** | Agent action audit | Trace ledger with same F1–F9 spine as portfolio |

**Win when:** buyer needs **production guardrails + trace audit**, not a hosted LLM.  
**Lose when:** buyer needs LangGraph ecosystem, vector DB, or NeMo safety inference.

---

## Competitive positioning

| Capability | LangChain defaults | Custom scripts | **AI Kit** |
|------------|-------------------|----------------|------------|
| Token bucket per provider | Plugin | DIY | **inst_spine rates** |
| Crash-safe resume | Varies | Manual | **Lamport checkpoints** |
| Structured output retry | Library-specific | Ad-hoc | **`validate_with_retry` in CLI** |
| Agent trace audit | Logs only | No | **Ledger + export + verify-bundle** |
| Rate limit errors | Exception string | N/A | **`RateLimitError` typed** |

---

## Architecture

```
rate limit → step_fn (buyer-supplied) → validate_with_retry
          → Lamport checkpoint → trace ledger append
          → F1–F9 check → export → verify-bundle
```

### Live LLM (optional)

```bash
export OPENAI_API_KEY=...
ai-kit run --live-llm --prompt "Summarize policy exception"
```

Stub mode default — no API key required for demo.

---

## CLI reference

```bash
pip install -e ".[dev,instpp]"
```

| Command | Purpose |
|---------|---------|
| `ai-kit run [--steps N] [--live-llm] [--trace-db PATH]` | Agent steps with checkpoint + trace |
| `ai-kit validate-demo --raw JSON` | Structured output validation demo |
| `ai-kit check [--database PATH]` | F1–F9 on trace ledger |
| `ai-kit export [--database PATH] [--tarball PATH]` | Audit bundle |
| `ai-kit verify-bundle --tarball PATH` | Offline auditor replay |

---

## Proof & diligence

```bash
./scripts/demo_ai_kit.sh
./scripts/instpp_rigorous_test.sh
ai-kit verify-bundle --tarball ./ai_kit_bundle.tar
```

| Artifact | Path |
|----------|------|
| Rigorous test log | `docs/test_logs/instpp_rigorous_latest.log` |
| Buyer one-pager | `docs/AI_KIT_BUYER.md` |
| Architecture | `src/ai_kit/README.md` |

---

## Non-goals (say no in RFPs)

- Not a hosted LLM (buyer supplies `step_fn` or `--live-llm` endpoint)
- Not NeMo / Bedrock / Llama Guard safety inference
- Not a vector DB or RAG platform
- Not a multi-agent orchestration UI

---


## RFP quick answers

| Question | Answer |
|----------|--------|
| Agent trace audit trail? | **Yes** — trace ledger + export |
| Crash-safe resume? | **Yes** — Lamport checkpoints |
| Rate limit fail-closed? | **Yes** — `RateLimitError` |
| Offline third-party verification? | **Yes** — `verify-bundle` |
| Hosted LLM included? | **No** — buyer model or OpenAI-compatible endpoint |
| LLM safety / content moderation? | **No** — upstream of agent |

---

## Related documents

- `docs/AI_KIT_BUYER.md` — one-page buyer sheet  
- `docs/BUYER_EVIDENCE_PACK.md` — procurement dry-run
