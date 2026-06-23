#!/usr/bin/env bash
# Copy updated Day-15 gate evaluator into /opt/trading-core.
#
#   sudo bash /opt/hibs-bet/deploy/sync-trading-day15-gate.sh
#   sudo bash /opt/hibs-racing/deploy/sync-trading-day15-gate.sh
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
NAME="evaluate_trading_day15_gate.py"

[[ -d "${TRADING}/scripts" ]] || { echo "missing ${TRADING}/scripts" >&2; exit 1; }

SRC=""
for candidate in \
  "${BET}/scripts/${NAME}" \
  "${RACING}/deploy/football-inst-overlay/scripts/${NAME}" \
  "${BET}/deploy/football-inst-overlay/scripts/${NAME}"; do
  if [[ -f "${candidate}" ]]; then
    SRC="${candidate}"
    break
  fi
done

if [[ -z "${SRC}" ]]; then
  echo "ERROR: ${NAME} not found under ${BET} or ${RACING} overlay" >&2
  exit 1
fi

install -m 755 "${SRC}" "${TRADING}/scripts/${NAME}"
echo "Installed ${TRADING}/scripts/${NAME} <- ${SRC}"

if [[ -x "${TRADING}/.venv/bin/python3" ]]; then
  cd "${TRADING}"
  PYTHONPATH=src "${TRADING}/.venv/bin/python3" "scripts/${NAME}" --help | head -5
fi
