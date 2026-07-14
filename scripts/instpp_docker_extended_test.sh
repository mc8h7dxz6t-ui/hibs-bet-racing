#!/usr/bin/env bash
# Docker extended live test — Redis + Postgres compose + full Inst++ proof on host.
# Logs to docs/test_logs/instpp_docker_extended_<timestamp>.log
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
COMPOSE="${COMPOSE:-docker compose -f docker-compose.instpp.yml}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

TS="$(date -u +%Y-%m-%dT%H%M%SZ)"
LOG_DIR="$ROOT/docs/test_logs"
LOG_FILE="$LOG_DIR/instpp_docker_extended_${TS}.log"
LATEST_LINK="$LOG_DIR/instpp_docker_extended_latest.log"
SUMMARY_FILE="$LOG_DIR/instpp_docker_extended_latest_summary.json"
REDIS_PORT="${INST_REDIS_PORT:-6379}"
POSTGRES_PORT="${INST_POSTGRES_PORT:-5432}"
WORKFLOW_PORT="${INST_WORKFLOW_PORT:-8790}"
KEEP_COMPOSE="${KEEP_COMPOSE:-0}"
STEPS_PASSED=()
STEPS_FAILED=()
SKIPPED_SECTIONS=()

mkdir -p "$LOG_DIR"
exec > >(tee -a "$LOG_FILE") 2>&1

pass_step() {
  echo "[PASS] $*"
  STEPS_PASSED+=("$1")
}

fail_step() {
  echo "[FAIL] $*"
  STEPS_FAILED+=("$1")
  exit 1
}

skip_step() {
  echo "[SKIP] $*"
  SKIPPED_SECTIONS+=("$1")
}

section() {
  echo ""
  echo "----------------------------------------------------------------"
  echo "SECTION: $*"
  echo "----------------------------------------------------------------"
}

cleanup_compose() {
  if [[ "$KEEP_COMPOSE" == "1" ]]; then
    echo "[INFO] KEEP_COMPOSE=1 — leaving compose stack running"
    return 0
  fi
  section "Compose tear-down"
  $COMPOSE --profile redis --profile extended down -v || true
}

trap cleanup_compose EXIT

echo "================================================================"
echo "INST++ DOCKER EXTENDED LIVE TEST"
echo "Started: $(date -u +%Y-%m-%dT%H:%M:%SZ) UTC"
echo "Log: $LOG_FILE"
echo "================================================================"

if ! command -v docker >/dev/null 2>&1; then
  fail_step "docker_cli" "docker not installed — install Docker or run CI job docker-extended"
fi

section "Compose up (redis + extended/postgres + inst-workflow)"
$COMPOSE --profile redis --profile extended up -d --wait
$COMPOSE --profile redis --profile extended ps

export INST_REDIS_URL="redis://127.0.0.1:${REDIS_PORT}/0"
export INST_TEST_POSTGRES_DSN="postgresql://instpp:instpp@127.0.0.1:${POSTGRES_PORT}/instpp_test"
export WEBHOOK_DISPATCH_MODE=redis
export INST_RIGOROUS_FAIL_ON_SKIP=1
export INST_REDIS_SOAK_ITERATIONS="${INST_REDIS_SOAK_ITERATIONS:-50}"

echo "INST_REDIS_URL=$INST_REDIS_URL"
echo "INST_TEST_POSTGRES_DSN=$INST_TEST_POSTGRES_DSN"
echo "WEBHOOK_DISPATCH_MODE=$WEBHOOK_DISPATCH_MODE"

section "Install dependencies"
pip install -e ".[dev,instpp]" -q
pass_step "install"

section "Proof-lite (profile gates + 12/12 verify)"
./scripts/instpp_proof_lite.sh
pass_step "proof_lite"

section "Smoke (institutional unit + integration)"
./scripts/instpp_smoke_test.sh
pass_step "smoke"

section "Rigorous E2E (zero-skip with Redis + Postgres)"
./scripts/instpp_rigorous_test.sh
pass_step "rigorous"

section "Redis production soak"
./scripts/instpp_redis_soak.sh
pass_step "redis_soak"

section "Postgres profile pytest"
"$PYTHON" -m pytest tests/test_postgres_profile.py -v --tb=short
pass_step "postgres_profile"

section "Workflow UI health (compose inst-workflow)"
for i in $(seq 1 36); do
  if curl -sf "http://127.0.0.1:${WORKFLOW_PORT}/health" >/dev/null; then
    curl -sf "http://127.0.0.1:${WORKFLOW_PORT}/health" || true
    pass_step "workflow_health"
    break
  fi
  if [[ "$i" -eq 36 ]]; then
    $COMPOSE --profile redis --profile extended logs inst-workflow || true
    fail_step "workflow_health" "inst-workflow /health not ready on :${WORKFLOW_PORT}"
  fi
  sleep 5
done

section "SOC2 evidence collector"
if [[ -f "./data/demo/portfolio/PORTFOLIO_MANIFEST.json" ]]; then
  "$PYTHON" ./scripts/soc2_evidence_collector.py \
    --manifest ./data/demo/portfolio/PORTFOLIO_MANIFEST.json \
    --out "$LOG_DIR/soc2_evidence_latest.json"
  pass_step "soc2_evidence"
else
  skip_step "soc2_evidence"
fi

ENDED_AT="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
RIGOROUS_SUMMARY="$LOG_DIR/instpp_rigorous_latest_summary.json"
STEPS_PASSED_JSON=$(printf '%s\n' "${STEPS_PASSED[@]:-}" | "$PYTHON" -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))")
STEPS_SKIPPED_JSON=$(printf '%s\n' "${SKIPPED_SECTIONS[@]:-}" | "$PYTHON" -c "import sys,json; print(json.dumps([l.strip() for l in sys.stdin if l.strip()]))")

SUMMARY_JSON=$("$PYTHON" -c "
import json
from pathlib import Path
rigorous_path = Path('$RIGOROUS_SUMMARY')
rigorous = json.loads(rigorous_path.read_text()) if rigorous_path.is_file() else {}
print(json.dumps({
    'suite': 'institutional_docker_extended',
    'status': 'PASSED',
    'finished_utc': '$ENDED_AT',
    'log_file': '$(basename "$LOG_FILE")',
    'compose_profiles': ['redis', 'extended'],
    'env': {
        'INST_REDIS_URL': '$INST_REDIS_URL',
        'INST_TEST_POSTGRES_DSN': '$INST_TEST_POSTGRES_DSN',
        'WEBHOOK_DISPATCH_MODE': 'redis',
        'INST_RIGOROUS_FAIL_ON_SKIP': '1',
    },
    'steps_passed': json.loads('''$STEPS_PASSED_JSON'''),
    'steps_skipped': json.loads('''$STEPS_SKIPPED_JSON'''),
    'rigorous_summary': rigorous,
    'zero_skip_expected': True,
}, indent=2))
")

echo ""
echo "$SUMMARY_JSON" | tee "$SUMMARY_FILE"
"$PYTHON" ./scripts/instpp_ci_autonomy_log.py \
  --suite docker-extended \
  --status PASSED \
  --skipped-sections "$(echo "$SUMMARY_JSON" | "$PYTHON" -c "import sys,json; print(json.dumps(json.load(sys.stdin).get('steps_skipped',[])))")" \
  --log-file "$(basename "$LOG_FILE")"

ln -sf "$(basename "$LOG_FILE")" "$LATEST_LINK"

echo ""
echo "================================================================"
echo "DOCKER EXTENDED LIVE TEST PASSED"
echo "Finished: $ENDED_AT UTC"
echo "Log: $LOG_FILE"
echo "Summary: $SUMMARY_FILE"
echo "================================================================"
