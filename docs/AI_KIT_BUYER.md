# AI Kit — Buyer Sheet

**One job:** Ship agentic AI features without rate-limit explosions, lost state, or unvalidated JSON blobs — with a tamper-evident trace ledger.

**Pitch:** *Run agents in production with checkpoints, rate limits, and an audit trail auditors can verify offline.*

---

## Buyer

| Segment | Pain | Institutional answer |
|---------|------|----------------------|
| Platform teams adding agents | Rate limits crash production | Token bucket via `inst_spine` rates + typed `RateLimitError` |
| ML / AI engineers | Lost state on worker crash | Lamport checkpoints + resume |
| Compliance / risk | “What did the agent do?” | AppendOnlyLedger trace + export |


---

## Tech edge (proof)

| Capability | Evidence |
|------------|----------|
| Structured output | `validate_with_retry` wired in `ai-kit run` |
| Checkpoints | Lamport-ordered resume from SQLite |
| Trace audit | `check` / `export` / `verify-bundle` on trace ledger |
| Rate limits | `RateLimitError` (not raw traceback) |

**Auditor dry-run:**
```bash
ai-kit run --steps 3 --trace-db ./trace.sqlite
ai-kit export --database ./trace.sqlite --tarball ./ai_kit_bundle.tar
ai-kit verify-bundle --tarball ./ai_kit_bundle.tar
```

---

## 60-second demo

```bash
./scripts/demo_ai_kit.sh
```

---

## Non-goals

- Not a hosted LLM (step_fn is buyer-supplied closure)
- Not NeMo / Bedrock / Llama Guard safety inference
- Not a vector DB or RAG platform

---

## CLI

| Command | Purpose |
|---------|---------|
| `run` | Agent steps with checkpoint + trace |
| `check` | F1–F9 on trace ledger |
| `export` | Audit bundle |
| `verify-bundle` | Offline auditor replay |
| `validate-demo` | Structured output validation demo |

See `src/ai_kit/README.md` for architecture.  
**Full spec:** `docs/AI_KIT_SALES_TECH_SPEC.md`

---

## Next step

| Step | Action |
|------|--------|
| 1 | `./scripts/demo_ai_kit.sh` (60s) |
| 2 | `ai-kit verify-bundle --tarball ./ai_kit_bundle.tar` |
| 3 | RFP depth → `docs/AI_KIT_SALES_TECH_SPEC.md` |
