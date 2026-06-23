# AI Kit (`ai_kit`)

Agent loop with Lamport checkpoints, structured output validation, and trace ledger export.

## Architecture

```
rate limit → step_fn → validate_with_retry → checkpoint → trace ledger → export
```

## Install

```bash
pip install -e ".[dev,instpp]"
```

## CLI

```bash
ai-kit run --steps 3 --trace-db data/ai_kit_trace.sqlite
ai-kit check --database data/ai_kit_trace.sqlite
ai-kit export --database data/ai_kit_trace.sqlite --tarball ai_kit_bundle.tar
ai-kit verify-bundle --tarball ai_kit_bundle.tar
ai-kit run --live-llm --prompt "..."   # requires OPENAI_API_KEY
ai-kit validate-demo --raw '{"ok":true}'
```

| Variable | Purpose |
|----------|---------|
| `OPENAI_API_KEY` | Live LLM inference |
| `AI_KIT_LLM_BASE_URL` | OpenAI-compatible base (default api.openai.com) |
| `AI_KIT_LLM_MODEL` | Model id (default gpt-4o-mini) |

## Demo

```bash
./scripts/demo_ai_kit.sh
```

## Buyer positioning

`docs/AI_KIT_BUYER.md`

## Gold standard

`docs/INSTITUTIONAL_STANDARD.md`
