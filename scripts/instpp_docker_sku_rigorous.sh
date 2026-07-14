#!/usr/bin/env bash
# Docker extreme rigorous matrix — isolated container per SKU, full logged proof.
# Logs: docs/test_logs/instpp_docker_sku_<sku>_<timestamp>.log
# Summary: docs/test_logs/instpp_docker_sku_latest_summary.json
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.instpp.yml}"
IMAGE="${INSTPP_DOCKER_IMAGE:-python:3.11-slim-bookworm}"
NETWORK="${INSTPP_DOCKER_NETWORK:-host}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

TS="$(date -u +%Y-%m-%dT%H%M%SZ)"
LOG_DIR="$ROOT/docs/test_logs"
SUMMARY_FILE="$LOG_DIR/instpp_docker_sku_latest_summary.json"
MASTER_LOG="$LOG_DIR/instpp_docker_sku_matrix_${TS}.log"
KEEP_COMPOSE="${KEEP_COMPOSE:-0}"

SKUS=(
  compliance
  proxy
  altdata
  ai-kit
  webhook-mesh
  ad-guard
  health
  model-governor
  drift-gate
  webhook-replay
  spend-guard
  agent-ledger
)

RESULTS=()
FAILED=()

mkdir -p "$LOG_DIR"
exec > >(tee -a "$MASTER_LOG") 2>&1

pass() { echo "[PASS] $*"; }
fail() { echo "[FAIL] $*"; exit 1; }

section() {
  echo ""
  echo "================================================================"
  echo "$*"
  echo "================================================================"
}

cleanup_compose() {
  if [[ "$KEEP_COMPOSE" == "1" ]]; then
    echo "[INFO] KEEP_COMPOSE=1 — leaving redis/postgres stack up"
    return 0
  fi
  section "Compose tear-down"
  $COMPOSE --profile redis --profile extended down -v || true
}

trap cleanup_compose EXIT

section "INST++ DOCKER SKU RIGOROUS MATRIX — 12 isolated containers"
echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ) UTC"
echo "Image: $IMAGE"
echo "Network: $NETWORK"
echo "Master log: $MASTER_LOG"

if ! command -v docker >/dev/null 2>&1; then
  fail "docker_cli" "docker not installed — run on CI or install Docker locally"
fi

section "Compose up (redis + postgres for scale-profile SKUs)"
$COMPOSE --profile redis --profile extended up -d --wait
export INST_REDIS_URL="${INST_REDIS_URL:-redis://127.0.0.1:${INST_REDIS_PORT:-6379}/0}"
export INST_TEST_POSTGRES_DSN="${INST_TEST_POSTGRES_DSN:-postgresql://instpp:instpp@127.0.0.1:${INST_POSTGRES_PORT:-5432}/instpp_test}"
export WEBHOOK_DISPATCH_MODE="${WEBHOOK_DISPATCH_MODE:-redis}"
export INST_RIGOROUS_FAIL_ON_SKIP="${INST_RIGOROUS_FAIL_ON_SKIP:-1}"
export SKIP_LIVE=1
export SKIP_LIVE_LLM=1

echo "INST_REDIS_URL=$INST_REDIS_URL"
echo "INST_TEST_POSTGRES_DSN=$INST_TEST_POSTGRES_DSN"

for SKU in "${SKUS[@]}"; do
  SKU_LOG="$LOG_DIR/instpp_docker_sku_${SKU}_${TS}.log"
  ln -sf "$(basename "$SKU_LOG")" "$LOG_DIR/instpp_docker_sku_${SKU}_latest.log"
  section "SKU $SKU — docker run (isolated)"
  set +e
  docker run --rm \
    --network "$NETWORK" \
    -v "$ROOT:/app" \
    -w /app \
    -e SKIP_LIVE=1 \
    -e SKIP_LIVE_LLM=1 \
    -e WEBHOOK_PROVIDER_SECRET=docker-rigorous-secret \
    -e INST_REDIS_URL="$INST_REDIS_URL" \
    -e INST_TEST_POSTGRES_DSN="$INST_TEST_POSTGRES_DSN" \
    -e WEBHOOK_DISPATCH_MODE="$WEBHOOK_DISPATCH_MODE" \
    -e INST_RIGOROUS_FAIL_ON_SKIP="$INST_RIGOROUS_FAIL_ON_SKIP" \
    -e DOCKER_SKU_WORK="/tmp/instpp_docker_sku_${SKU}" \
    "$IMAGE" \
    bash -lc "chmod +x ./scripts/docker_sku_rigorous_one.sh && ./scripts/docker_sku_rigorous_one.sh '$SKU'" \
    2>&1 | tee "$SKU_LOG"
  RC=${PIPESTATUS[0]}
  set -e
  if [[ "$RC" -eq 0 ]]; then
    pass "$SKU"
    RESULTS+=("{\"sku\":\"$SKU\",\"ok\":true,\"log\":\"$(basename "$SKU_LOG")\"}")
  else
    echo "[FAIL] $SKU (exit $RC) — see $SKU_LOG"
    FAILED+=("$SKU")
    RESULTS+=("{\"sku\":\"$SKU\",\"ok\":false,\"log\":\"$(basename "$SKU_LOG")\",\"exit_code\":$RC}")
  fi
done

ENDED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
STATUS="PASSED"
if [[ ${#FAILED[@]} -gt 0 ]]; then
  STATUS="FAILED"
fi

RESULTS_JSON=$(printf '%s\n' "${RESULTS[@]}" | "$PYTHON" -c "import sys,json; print(json.dumps([json.loads(l) for l in sys.stdin if l.strip()]))")
FAILED_JSON=$(printf '%s\n' "${FAILED[@]:-}" | "$PYTHON" -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))")

SUMMARY_JSON=$("$PYTHON" -c "
import json
print(json.dumps({
    'suite': 'institutional_docker_sku_rigorous',
    'status': '$STATUS',
    'finished_utc': '$ENDED_AT',
    'master_log': '$(basename "$MASTER_LOG")',
    'docker_image': '$IMAGE',
    'skus_total': 12,
    'skus_passed': 12 - len(json.loads('''$FAILED_JSON''')),
    'skus_failed': json.loads('''$FAILED_JSON'''),
    'results': json.loads('''$RESULTS_JSON'''),
    'env': {
        'INST_REDIS_URL': '$INST_REDIS_URL',
        'INST_TEST_POSTGRES_DSN': '$INST_TEST_POSTGRES_DSN',
        'INST_RIGOROUS_FAIL_ON_SKIP': '$INST_RIGOROUS_FAIL_ON_SKIP',
        'SKIP_LIVE': '1',
    },
    'per_sku_logs': 'docs/test_logs/instpp_docker_sku_<sku>_*.log',
}, indent=2))
")

echo ""
echo "$SUMMARY_JSON" | tee "$SUMMARY_FILE"
"$PYTHON" ./scripts/instpp_ci_autonomy_log.py \
  --suite docker-sku-rigorous \
  --status "$STATUS" \
  --log-file "$(basename "$MASTER_LOG")" \
  --skipped-sections "[]" || true

ln -sf "$(basename "$MASTER_LOG")" "$LOG_DIR/instpp_docker_sku_matrix_latest.log"

section "FINISHED — $STATUS"
echo "Summary: $SUMMARY_FILE"

if [[ "$STATUS" != "PASSED" ]]; then
  exit 1
fi
