#!/usr/bin/env bash
# Institutional++ stack boundaries — three isolated VPS roots, one explicit cross-link layer.
# Source from deploy scripts; do not rsync across product roots.
#
#   source "$(dirname "${BASH_SOURCE[0]}")/lib_stack_boundaries.sh"
#
set -euo pipefail

# VPS install roots (never symlink one into another)
readonly HIBS_FOOTBALL_ROOT="${HIBS_FOOTBALL_ROOT:-/opt/hibs-bet}"
readonly HIBS_RACING_ROOT="${HIBS_RACING_ROOT:-/opt/hibs-racing}"
readonly HIBS_TRADING_ROOT="${HIBS_TRADING_ROOT:-/opt/trading-core}"

# Secrets (trading only — never copy into football .env)
readonly HIBS_TRADING_SECRETS="${HIBS_TRADING_SECRETS:-/etc/trading_secrets}"

# systemd units (one product each)
readonly HIBS_FOOTBALL_UNIT="${HIBS_FOOTBALL_UNIT:-hibs-bet.service}"
readonly HIBS_RACING_UNIT="${HIBS_RACING_UNIT:-hibs-racing.service}"
readonly HIBS_TRADING_SHADOW_UNIT="${HIBS_TRADING_SHADOW_UNIT:-trading-shadow-soak.service}"
readonly HIBS_TRADING_PAPER_UNIT="${HIBS_TRADING_PAPER_UNIT:-trading-paper.service}"

# Listen ports (localhost upstreams)
readonly HIBS_FOOTBALL_PORT="${HIBS_FOOTBALL_PORT:-8000}"
readonly HIBS_RACING_PORT="${HIBS_RACING_PORT:-5003}"
readonly HIBS_TRADING_SHADOW_PORT="${HIBS_TRADING_SHADOW_PORT:-9108}"
readonly HIBS_TRADING_PAPER_PORT="${HIBS_TRADING_PAPER_PORT:-9109}"

# Cross-link keys allowed in football .env (URL pointers + non-secret trading display config)
readonly HIBS_CROSS_LINK_KEYS=(
  HIBS_RACING_BASE_URL
  HIBS_PORTFOLIO_API_URL
  HIBS_TRADING_STATUS_URL
  TRADING_METRICS_URL
  TRADING_ENABLE_CRYPTO
  STRATEGY_CRYPTO_SYMBOLS
  STRATEGY_SYMBOLS
  CRYPTO_MARKET_DATA_SOURCE
  TRADING_DEPLOYMENT_PHASE
  TRADING_PROFILE
)

stack_assert_football_only() {
  local path="$1"
  if [[ "${path}" == "${HIBS_RACING_ROOT}"/* ]] || [[ "${path}" == "${HIBS_TRADING_ROOT}"/* ]]; then
    echo "BOUNDARY: football deploy must not write under racing/trading root: ${path}" >&2
    return 1
  fi
}

stack_assert_racing_only() {
  local path="$1"
  if [[ "${path}" == "${HIBS_FOOTBALL_ROOT}"/* ]] || [[ "${path}" == "${HIBS_TRADING_ROOT}"/* ]]; then
    echo "BOUNDARY: racing deploy must not write under football/trading root: ${path}" >&2
    return 1
  fi
}

stack_assert_trading_only() {
  local path="$1"
  if [[ "${path}" == "${HIBS_FOOTBALL_ROOT}"/* ]] || [[ "${path}" == "${HIBS_RACING_ROOT}"/* ]]; then
    echo "BOUNDARY: trading deploy must not write under football/racing root: ${path}" >&2
    return 1
  fi
}
