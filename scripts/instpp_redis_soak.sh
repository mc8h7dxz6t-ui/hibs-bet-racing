#!/usr/bin/env bash
# Redis production profile soak — requires INST_REDIS_URL.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
ITERATIONS="${INST_REDIS_SOAK_ITERATIONS:-200}"
export INST_REDIS_SOAK_ITERATIONS="$ITERATIONS"

if [[ -z "${INST_REDIS_URL:-}" ]]; then
  echo "[SKIP] INST_REDIS_URL unset"
  exit 0
fi

echo "==> Redis soak (${ITERATIONS} iterations)"
"$PYTHON" -m pytest tests/test_redis_soak.py -v --tb=short
echo "[PASS] Redis soak"
