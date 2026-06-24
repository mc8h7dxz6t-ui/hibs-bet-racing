#!/usr/bin/env bash
# Guided portfolio demo for screen-recording — all 8 products with narration prompts.
# Usage: ./scripts/record_portfolio_demo_video.sh [--clean]
# Script: docs/DEMO_VIDEO_PORTFOLIO_ALL.md
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

_intro() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  PORTFOLIO VIDEO RECORDING — read docs/DEMO_VIDEO_PORTFOLIO_ALL.md"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""
  read -r -p "Press Enter when OBS/Loom is recording… "
}

_outro() {
  echo ""
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
  echo "  [END] SAY: Eight products, one proof spine — pilot from £2.5k"
  echo "  [END] Show title card with your contact"
  echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
}

_intro

export PAUSE=1
export SKIP_LIVE="${SKIP_LIVE:-1}"
export SKIP_LIVE_LLM=1
export WEBHOOK_PROVIDER_SECRET=demo-secret

ARGS=()
if [[ "${1:-}" == "--clean" ]]; then
  ARGS+=(--clean)
fi

./scripts/demo_portfolio_all.sh "${ARGS[@]}"

_outro
