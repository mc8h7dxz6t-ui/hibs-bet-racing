#!/usr/bin/env bash
# AI Kit demo — stub run or live LLM when OPENAI_API_KEY is set.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
TRACE="${1:-./data/demo/ai_kit_trace.sqlite}"
TAR="${2:-./data/demo/ai_kit_bundle.tar}"
CHECKPOINT="${3:-./data/demo/ai_kit_checkpoint.sqlite}"
mkdir -p "$(dirname "$TRACE")" "$(dirname "$TAR")" "$(dirname "$CHECKPOINT")"
RUN_ARGS=(run --steps 2 --trace-db "$TRACE" --checkpoint-db "$CHECKPOINT" --max-tokens 256)
if [ -n "${OPENAI_API_KEY:-}" ] && [ "${SKIP_LIVE_LLM:-0}" != "1" ]; then
  echo "── 1/4 Agent run (live LLM) ──"
  RUN_ARGS+=(--live-llm --prompt "Summarize institutional audit readiness in one sentence.")
else
  echo "── 1/4 Agent run (stub — set OPENAI_API_KEY for live LLM) ──"
fi
"$PYTHON" -m ai_kit.cli "${RUN_ARGS[@]}"
echo "── 2/4 F1–F9 check ──"
"$PYTHON" -m ai_kit.cli check --database "$TRACE"
echo "── 3/4 Export bundle ──"
"$PYTHON" -m ai_kit.cli export --database "$TRACE" --tarball "$TAR"
echo "── 4/4 Verify offline ──"
"$PYTHON" -m ai_kit.cli verify-bundle --tarball "$TAR"
echo "[PASS] AI Kit demo → $TAR"
