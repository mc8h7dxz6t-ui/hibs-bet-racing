#!/usr/bin/env bash
# Load Institutional++ environment — safe to source from any instpp script.
# Creates nothing; copies .env.instpp.example → .env.instpp on first run if missing.

_instpp_env_root() {
  if [[ -n "${INSTPP_ROOT:-}" ]]; then
    printf '%s' "$INSTPP_ROOT"
    return 0
  fi
  local here
  here="$(cd "$(dirname "${BASH_SOURCE[1]:-${BASH_SOURCE[0]}}")/.." && pwd)"
  printf '%s' "$here"
}

instpp_load_env() {
  local root
  root="$(_instpp_env_root)"
  export INSTPP_ROOT="$root"

  if [[ ! -f "$root/.env.instpp" && -f "$root/.env.instpp.example" ]]; then
    cp "$root/.env.instpp.example" "$root/.env.instpp"
    echo "[instpp] Created $root/.env.instpp from example (offline defaults)" >&2
  fi

  if [[ -f "$root/.env.instpp" ]]; then
    set -a
    # shellcheck disable=SC1091
    source "$root/.env.instpp"
    set +a
  fi

  # Normalize relative demo paths to repo root.
  for var in PORTFOLIO_DEMO_DIR PHASE2_DEMO_DIR GOLD_DEMO_DIR WEBHOOK_MESH_LEDGER \
    WEBHOOK_REPLAY_CAPTURE_DIR INST_COMPLIANCE_DB INST_PROXY_DB INST_EXPORT_DIR; do
    local val="${!var:-}"
    [[ -n "$val" && "$val" != /* ]] || continue
    export "$var=$root/${val#./}"
  done
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  instpp_load_env
  echo "[OK] instpp environment loaded from ${INSTPP_ROOT:-.}/.env.instpp"
  env | grep -E '^(SKIP_LIVE|PORTFOLIO_DEMO|WEBHOOK_|INST_|GOLD_DEMO)' | sort || true
fi
