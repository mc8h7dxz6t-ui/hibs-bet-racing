#!/usr/bin/env bash
# Source stack boundary constants from the correct VPS path (scripts/ or deploy/ fallback).
_stack_bootstrap_root() {
  echo "${DEPLOY_PATH:-/opt/hibs-bet}"
}

source_lib_stack_bootstrap() {
  local root
  root="$(_stack_bootstrap_root)"
  if [[ -f "${root}/scripts/lib_stack_bootstrap.sh" ]]; then
    return 0
  fi
  if [[ -f "${root}/deploy/lib_stack_bootstrap.sh" ]]; then
    mkdir -p "${root}/scripts"
    cp "${root}/deploy/lib_stack_bootstrap.sh" "${root}/scripts/lib_stack_bootstrap.sh"
    return 0
  fi
  return 1
}

source_lib_stack_boundaries() {
  local root
  root="$(_stack_bootstrap_root)"
  source_lib_stack_bootstrap || true
  if [[ -f "${root}/scripts/lib_stack_boundaries.sh" ]]; then
    # shellcheck source=scripts/lib_stack_boundaries.sh
    source "${root}/scripts/lib_stack_boundaries.sh"
    return 0
  fi
  if [[ -f "${root}/deploy/lib_stack_boundaries.sh" ]]; then
    mkdir -p "${root}/scripts"
    cp "${root}/deploy/lib_stack_boundaries.sh" "${root}/scripts/lib_stack_boundaries.sh"
    # shellcheck source=scripts/lib_stack_boundaries.sh
    source "${root}/scripts/lib_stack_boundaries.sh"
    return 0
  fi
  echo "ERROR: lib_stack_boundaries.sh missing under ${root}/scripts and ${root}/deploy" >&2
  echo "       Re-run: bash scripts/ensure_deploy_assets.sh && ./scripts/deploy_racing_to_vps.sh" >&2
  return 1
}

source_lib_trading_probe() {
  local root
  root="$(_stack_bootstrap_root)"
  if [[ -f "${root}/scripts/lib_trading_probe.sh" ]]; then
    # shellcheck source=scripts/lib_trading_probe.sh
    source "${root}/scripts/lib_trading_probe.sh"
    return 0
  fi
  if [[ -f "${root}/deploy/lib_trading_probe.sh" ]]; then
    mkdir -p "${root}/scripts"
    cp "${root}/deploy/lib_trading_probe.sh" "${root}/scripts/lib_trading_probe.sh"
    # shellcheck source=scripts/lib_trading_probe.sh
    source "${root}/scripts/lib_trading_probe.sh"
    return 0
  fi
  return 1
}
