#!/usr/bin/env bash
# Unified evidence + ops status across football, racing, trading.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
if [[ "${1:-}" == "--remote" ]]; then
  HOST="${DEPLOY_HOST:-77.68.89.73}"
  USER="${DEPLOY_USER:-root}"
  exec ssh -o BatchMode=yes -o ConnectTimeout=30 "${USER}@${HOST}" \
    "bash '${ROOT}/scripts/all_evidence_status.sh' --json"
fi
PY="${ROOT}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"
if [[ -f "${ROOT}/.env" ]]; then set -a; source "${ROOT}/.env"; set +a; fi
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
if [[ "${1:-}" == "--json" ]]; then
  exec "${PY}" "${ROOT}/scripts/all_evidence_status.py" --json
fi
"${PY}" "${ROOT}/scripts/all_evidence_status.py"
echo ""
bash "${ROOT}/scripts/verify_football_evidence_gates.sh" 2>/dev/null | head -18 || true
echo ""
bash "${ROOT}/scripts/verify_racing_evidence_gates.sh" 2>/dev/null | head -18 || true
echo ""
bash "${ROOT}/scripts/verify_inplay_evidence_gates.sh" 2>/dev/null | head -18 || true
