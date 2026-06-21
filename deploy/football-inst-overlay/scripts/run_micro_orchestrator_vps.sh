#!/usr/bin/env bash
# VPS systemd ExecStart for trading-micro — small real-capital lane (:9110).
set -euo pipefail

INSTALL_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$INSTALL_ROOT"

PYTHON="${INSTALL_ROOT}/.venv/bin/python3"
DB_PATH="${TRADING_MICRO_DB:-${INSTALL_ROOT}/data/trading_micro.db}"
STRATEGY_AUDIT="${TRADING_MICRO_STRATEGY_AUDIT:-${INSTALL_ROOT}/data/strategy_scan_micro.jsonl}"
SPREAD_AUDIT="${TRADING_MICRO_SPREAD_AUDIT:-${INSTALL_ROOT}/data/spread_slippage_micro.jsonl}"
EQUITY_SYMBOLS="${STRATEGY_SYMBOLS:-AAPL,TSLA}"
FEED="${MARKET_STREAM_FEED:-iex}"

echo "[trading-micro] phase=micro caps \$100/order \$500 gross — metrics :${METRICS_PORT:-9110}" >&2

STREAM_ARGS=(--enable-market-stream --market-stream-feed "$FEED" --stream-symbols "$EQUITY_SYMBOLS")
if systemctl is-active --quiet trading-shadow-soak 2>/dev/null; then
  STREAM_ARGS=()
  echo "[trading-micro] shadow-soak holds Alpaca WSS — micro equity stream off" >&2
elif systemctl is-active --quiet trading-paper 2>/dev/null; then
  STREAM_ARGS=()
  echo "[trading-micro] trading-paper active — disable paper or shadow before micro stream" >&2
fi

args=(
  "$PYTHON" scripts/run_trading_orchestrator.py
  --broker alpaca
  --deployment-phase micro
  --db-path "$DB_PATH"
  --strategy-symbols "$EQUITY_SYMBOLS"
  --enable-strategy-runner
  --strategy-audit-log "$STRATEGY_AUDIT"
  --spread-slippage-audit "$SPREAD_AUDIT"
  --assumed-spread-bps "${ASSUMED_SPREAD_BPS:-10}"
  --metrics-port "${METRICS_PORT:-9110}"
  --gate-min-paper-days 0
  --gate-min-shadow-days 0
  --allow-broker-seed
)
if [[ ${#STREAM_ARGS[@]} -gt 0 ]]; then
  args+=("${STREAM_ARGS[@]}")
fi

exec "${args[@]}"
