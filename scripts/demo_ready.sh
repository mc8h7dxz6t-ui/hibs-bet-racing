#!/usr/bin/env bash
# Preflight — confirm environment is ready to plug / demo / run all 11 SKUs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap

SKIP_INSTALL="${SKIP_INSTALL:-0}"
FAIL=0

ok() { echo "[OK]  $*"; }
warn() { echo "[WARN] $*" >&2; }
fail() { echo "[FAIL] $*" >&2; FAIL=1; }

step() { echo ""; echo "── $* ──"; }

step "Python"
ok "$("$PYTHON" --version 2>&1)"

if [[ "$SKIP_INSTALL" != "1" ]]; then
  step "Install inst++ extras"
  pip install -e ".[dev,instpp]" -q
  ok "pip install -e \".[dev,instpp]\""
else
  warn "SKIP_INSTALL=1 — not running pip install"
fi

step "CLI entry points (11 SKUs)"
CLIS=(
  compliance-log proxy-risk altdata ai-kit webhook-mesh
  ad-guard health-telemetry model-governor
  drift-gate webhook-replay spend-guard
)
for cli in "${CLIS[@]}"; do
  if command -v "$cli" >/dev/null 2>&1; then
    ok "$cli"
  elif "$PYTHON" -m pip show hibs-racing >/dev/null 2>&1; then
    # Editable install — module path fallback
    mod="${cli//-/_}"
    if "$PYTHON" -c "import importlib.util; import sys; sys.exit(0 if importlib.util.find_spec('${mod}') else 1)" 2>/dev/null; then
      ok "$cli (module)"
    else
      fail "missing CLI: $cli"
    fi
  else
    fail "missing CLI: $cli (run: make install)"
  fi
done

step "Demo scripts executable"
for script in scripts/demo_*.sh scripts/instpp_*.sh scripts/chaos_instpp.sh; do
  [[ -f "$script" ]] || continue
  if [[ -x "$script" ]]; then
    ok "$(basename "$script")"
  else
    chmod +x "$script"
    ok "$(basename "$script") (chmod +x)"
  fi
done

step "Core imports"
"$PYTHON" - <<'PY' || fail "core import check"
mods = [
    "inst_spine", "compliance_log", "proxy_risk", "altdata", "ai_kit",
    "webhook_mesh", "ad_guard", "health_telemetry", "model_governor",
    "drift_gate", "webhook_replay", "spend_guard", "inst_workflow",
]
for m in mods:
    __import__(m)
print("all modules import")
PY

step "Data directories"
mkdir -p data/demo/portfolio data/demo/phase2 data/demo/spend_gold .demo
ok "data/demo/* + .demo/"

step "Optional: Redis (INST_REDIS_URL)"
if [[ -n "${INST_REDIS_URL:-}" ]]; then
  if "$PYTHON" -c "import redis; r=redis.from_url('${INST_REDIS_URL}'); r.ping()" 2>/dev/null; then
    ok "Redis reachable at INST_REDIS_URL"
  else
    warn "INST_REDIS_URL set but ping failed — file-backed state still works"
  fi
else
  ok "INST_REDIS_URL unset — file-backed rolling state (default)"
fi

echo ""
if [[ "$FAIL" -eq 0 ]]; then
  echo "╔══════════════════════════════════════════════════════════════╗"
  echo "║  DEMO READY — run: make demo-all  or  make demo-gold         ║"
  echo "╚══════════════════════════════════════════════════════════════╝"
  echo ""
  echo "  make demo-all      # all 11 SKUs → data/demo/portfolio/"
  echo "  make demo-gold     # spend-plane sales walkthrough (11 steps)"
  echo "  make rigorous      # 11/11 E2E with logged summary"
  echo "  docs/RUN_DEMO.md"
  exit 0
fi

echo ""
echo "[FAIL] Preflight failed — fix issues above, then: make demo-ready"
exit 1
