#!/usr/bin/env bash
# Resolve consolidated vs split-stack host layout (/etc/hibs-bet/stack.env).
#
#   source scripts/lib_stack_host.sh
#   stack_load_env
#   echo "${FVE_HOST}" "${STACK_FVE_LOCAL}"
stack_load_env() {
  APP="${DEPLOY_PATH:-/opt/hibs-bet}"
  STACK_ENV="${HIBS_STACK_ENV:-/etc/hibs-bet/stack.env}"
  FVE_HOST="${FVE_REMOTE_HOST:-}"
  PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
  VPS_IP="${HIBS_VPS_IP:-}"
  if [[ -f "${STACK_ENV}" ]]; then
    # shellcheck disable=SC1090
    source "${STACK_ENV}"
    FVE_HOST="${FVE_REMOTE_HOST:-${FVE_HOST}}"
    PUBLIC="${HIBS_PUBLIC_HOST:-${PUBLIC}}"
    VPS_IP="${HIBS_VPS_IP:-${VPS_IP}}"
  fi
  FVE_HOST="${FVE_HOST:-77.68.89.75}"
  FVE_PORT="${FVE_API_PORT:-8010}"
  STACK_FVE_LOCAL=0
  case "${FVE_HOST}" in
    127.0.0.1|localhost|::1) STACK_FVE_LOCAL=1 ;;
  esac
  if [[ -n "${VPS_IP}" && "${FVE_HOST}" == "${VPS_IP}" ]]; then
    STACK_FVE_LOCAL=1
  fi
}
