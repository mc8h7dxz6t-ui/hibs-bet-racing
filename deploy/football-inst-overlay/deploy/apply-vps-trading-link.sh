#!/usr/bin/env bash
# Trading product link ONLY: verify localhost daemon; cross-links via apply-vps-site-cross-links.sh.
# Does NOT modify /opt/hibs-racing or copy trading code into football tree.
set -euo pipefail

LIB_ROOT="${DEPLOY_PATH:-/opt/hibs-bet}"
mkdir -p "${LIB_ROOT}/scripts"
for f in lib_stack_bootstrap.sh lib_stack_boundaries.sh lib_trading_probe.sh; do
  if [[ ! -f "${LIB_ROOT}/scripts/${f}" && -f "${LIB_ROOT}/deploy/${f}" ]]; then
    cp "${LIB_ROOT}/deploy/${f}" "${LIB_ROOT}/scripts/${f}"
  fi
done
# shellcheck source=scripts/lib_stack_bootstrap.sh
source "${LIB_ROOT}/scripts/lib_stack_bootstrap.sh"
source_lib_stack_boundaries

DOMAIN="${HIBS_DOMAIN:-hibs-bet.co.uk}"

stack_assert_trading_only "${HIBS_TRADING_ROOT}"

echo "==> Trading daemon (${HIBS_TRADING_ROOT}) — localhost metrics only"
shadow_up=0
paper_up=0
if systemctl is-active --quiet "${HIBS_TRADING_SHADOW_UNIT}" 2>/dev/null; then
  shadow_up=1
  echo "    ${HIBS_TRADING_SHADOW_UNIT}: active (:${HIBS_TRADING_SHADOW_PORT})"
fi
if systemctl is-active --quiet "${HIBS_TRADING_PAPER_UNIT}" 2>/dev/null; then
  paper_up=1
  echo "    ${HIBS_TRADING_PAPER_UNIT}: active (:${HIBS_TRADING_PAPER_PORT})"
fi
if [[ "${paper_up}" -eq 1 ]]; then
  metrics_port="${HIBS_TRADING_PAPER_PORT}"
elif [[ "${shadow_up}" -eq 1 ]]; then
  metrics_port="${HIBS_TRADING_SHADOW_PORT}"
else
  echo "    WARN: no trading systemd unit active — run link_trading_production.sh or link_paper_trading.sh"
  metrics_port="${HIBS_TRADING_SHADOW_PORT}"
fi
if [[ "${shadow_up}" -eq 1 && "${paper_up}" -eq 1 ]]; then
  echo "    dual mode: shadow evidence :${HIBS_TRADING_SHADOW_PORT}, dashboard → paper :${HIBS_TRADING_PAPER_PORT}"
fi

if source_lib_trading_probe; then
  probe="$(trading_probe_wait_ready "${metrics_port}" 30)"
  case "${probe}" in
    ready)
      echo "    metrics :${metrics_port}/ready: NODE_READY"
      ;;
    warming:*)
      echo "    metrics :${metrics_port}/ready: warming (${probe#warming:}) — /live OK; dashboard may show amber until feeds settle"
      ;;
    live)
      echo "    metrics :${metrics_port}/live: NODE_ALIVE (/ready still warming)"
      ;;
    *)
      echo "    WARN: :${metrics_port} not responding — check journalctl -u ${HIBS_TRADING_SHADOW_UNIT}"
      ;;
  esac
else
  echo "    WARN: lib_trading_probe.sh missing — skip metrics probe"
fi

echo "==> Site cross-links (football .env URL pointers — separate layer)"
export DEPLOY_PATH="${LIB_ROOT}"
export CROSS_LINK_RACING=auto
export CROSS_LINK_TRADING=1
bash "${LIB_ROOT}/deploy/apply-vps-site-cross-links.sh"

echo "==> Trading link applied — verify: https://${DOMAIN}/harvested-execution"
