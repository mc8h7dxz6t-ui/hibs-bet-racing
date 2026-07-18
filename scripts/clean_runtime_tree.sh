#!/usr/bin/env bash
# Purge transient runtime artifacts from the hibs-bet-racing working tree.
#
#   bash scripts/clean_runtime_tree.sh
#   bash scripts/clean_runtime_tree.sh --dry-run
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"

DRY_RUN=0
for arg in "$@"; do
  [[ "${arg}" == "--dry-run" ]] && DRY_RUN=1
done

log() { echo "[clean-runtime] $*"; }
run_rm() {
  if [[ "${DRY_RUN}" -eq 1 ]]; then
    log "would remove: $*"
  else
    rm -rf "$@"
  fi
}

log "root=${ROOT}"

if [[ -d Library ]]; then
  run_rm Library
fi

while IFS= read -r -d '' f; do
  run_rm "${f}"
done < <(find "${ROOT}" \
  -path "${ROOT}/.git" -prune -o \
  -path "${ROOT}/.venv" -prune -o \
  -path "${ROOT}/venv" -prune -o \
  -name '*.db' -type f -print0 2>/dev/null)

while IFS= read -r -d '' f; do
  run_rm "${f}"
done < <(find "${ROOT}" \
  -path "${ROOT}/.git" -prune -o \
  -path "${ROOT}/.venv" -prune -o \
  -path "${ROOT}/venv" -prune -o \
  -name '*.sqlite-journal' -type f -print0 2>/dev/null)

run_rm .pytest_cache __pycache__ .cache tmp .demo 2>/dev/null || true
find "${ROOT}" -type d -name '__pycache__' \
  -not -path '*/.git/*' -not -path '*/.venv/*' -print0 2>/dev/null | while IFS= read -r -d '' d; do
  run_rm "${d}"
done

log "done"
