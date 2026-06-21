#!/usr/bin/env bash
# Harvested Execution — install MICRO phase systemd unit (metrics :9110).
#
# Usage:
#   sudo bash deploy/install-harvested-execution-micro.sh --install-root /opt/trading-core
#
# Recommended: evaluate promotion first:
#   python3 scripts/evaluate_promotion_scorecard.py --transition shadow_to_micro \
#     --evidence-daily-dir /opt/trading-core/data/evidence/daily \
#     --metrics-url http://127.0.0.1:9108 --phase3-gate-passed
set -euo pipefail

INSTALL_ROOT="${INSTALL_ROOT:-/opt/trading-core}"
HIBS_ROOT="${HIBS_BET_ROOT:-/opt/hibs-bet}"
DRY_RUN=0
START_UNITS=1
RUN_PREFLIGHT=1
SKIP_SCORECARD=0

usage() {
  cat <<'EOF'
Harvested Execution micro-capital installer

  --install-root PATH     Install root (default: /opt/trading-core)
  --hibs-root PATH        Football app root for TRADING_METRICS_URL (default: /opt/hibs-bet)
  --dry-run               Print actions only
  --no-start              Install unit without enabling
  --skip-preflight        Skip Phase 3 gate
  --skip-scorecard        Skip shadow→micro scorecard check (not recommended)

Micro uses metrics port 9110 ($100/order, $500 gross caps in code).
Docs: docs/TRADING_PROMOTION_SCORECARD.md
EOF
}

log() { echo "[harvested-micro] $*"; }
die() { echo "[harvested-micro] FATAL: $*" >&2; exit 1; }

run() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    log "DRY-RUN: $*"
  else
    "$@"
  fi
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --install-root) INSTALL_ROOT="$2"; shift 2 ;;
    --hibs-root) HIBS_ROOT="$2"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --no-start) START_UNITS=0; shift ;;
    --skip-preflight) RUN_PREFLIGHT=0; shift ;;
    --skip-scorecard) SKIP_SCORECARD=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) die "Unknown option: $1" ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || die "Run as root: sudo bash deploy/install-harvested-execution-micro.sh"

REPO_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -d "$INSTALL_ROOT/src/hibs_predictor/trading_core" ]] || INSTALL_ROOT="$REPO_SRC"

if [[ -x "$INSTALL_ROOT/.venv/bin/python3" ]]; then
  PYTHON="$INSTALL_ROOT/.venv/bin/python3"
else
  PYTHON="$(command -v python3)"
fi

DATA_DIR="$INSTALL_ROOT/data"
SECRETS_FILE="/etc/trading_secrets"
SYSTEMD_DIR="/etc/systemd/system"
METRICS_PORT=9110

run useradd -r -s /usr/sbin/nologin trading_executor 2>/dev/null || true
run groupadd -f trading_ops 2>/dev/null || true
run usermod -aG trading_ops trading_executor 2>/dev/null || true
run mkdir -p "$DATA_DIR/evidence/daily"
run chown -R trading_executor:trading_ops "$DATA_DIR"

if [[ ! -f "$SECRETS_FILE" ]]; then
  log "Creating $SECRETS_FILE from template"
  run cp "$REPO_SRC/deploy/trading_secrets.template" "$SECRETS_FILE"
  run chmod 600 "$SECRETS_FILE"
fi

if [[ "$SKIP_SCORECARD" -eq 0 && "$DRY_RUN" -eq 0 ]]; then
  log "Shadow→micro promotion scorecard..."
  if ! "$PYTHON" "$INSTALL_ROOT/scripts/evaluate_promotion_scorecard.py" \
    --transition shadow_to_micro \
    --evidence-daily-dir "$DATA_DIR/evidence/daily" \
    --db-path "$DATA_DIR/trading_shadow_soak.db" \
    --shadow-soak-audit "$DATA_DIR/shadow_soak_audit.log" \
    --strategy-audit "$DATA_DIR/strategy_scan_audit.jsonl" \
    --spread-audit "$DATA_DIR/spread_slippage_audit.jsonl" \
    --metrics-url "http://127.0.0.1:9108" \
    --phase3-gate-passed 2>/dev/null; then
    die "Promotion scorecard NO-GO — use --skip-scorecard only for dry dev installs"
  fi
  log "Promotion scorecard GO"
fi

sed -e "s|/opt/trading-core|$INSTALL_ROOT|g" \
    -e "s|/opt/trading-core/.venv/bin/python3|$PYTHON|g" \
    "$REPO_SRC/deploy/trading-micro.service" > /tmp/trading-micro.service

run chmod +x "$INSTALL_ROOT/scripts/run_micro_orchestrator_vps.sh" \
  "$INSTALL_ROOT/scripts/verify_paper_preflight_vps.sh" 2>/dev/null || true

run cp /tmp/trading-micro.service "$SYSTEMD_DIR/trading-micro.service"
run systemctl daemon-reload

if [[ "$RUN_PREFLIGHT" -eq 1 && "$DRY_RUN" -eq 0 ]]; then
  HMAC="$(grep -E '^TRADING_HMAC_SECRET=' "$SECRETS_FILE" 2>/dev/null | cut -d= -f2- || echo preflight-dev)"
  run sudo -u trading_executor env \
    PYTHONPATH="$INSTALL_ROOT/src" \
    TRADING_HMAC_SECRET="$HMAC" \
    "$PYTHON" "$INSTALL_ROOT/scripts/run_phase3_gate.py" \
    --db-path "$DATA_DIR/trading_ci_gate.db" || die "Phase 3 gate failed"
fi

if [[ -f "$HIBS_ROOT/.env" && "$DRY_RUN" -eq 0 ]]; then
  log "Point hibs dashboard at micro metrics :${METRICS_PORT}"
  if grep -q '^TRADING_METRICS_URL=' "$HIBS_ROOT/.env"; then
    sed -i "s|^TRADING_METRICS_URL=.*|TRADING_METRICS_URL=http://127.0.0.1:${METRICS_PORT}|" "$HIBS_ROOT/.env"
  else
    echo "TRADING_METRICS_URL=http://127.0.0.1:${METRICS_PORT}" >> "$HIBS_ROOT/.env"
  fi
  if grep -q '^TRADING_DEPLOYMENT_PHASE=' "$HIBS_ROOT/.env"; then
    sed -i 's|^TRADING_DEPLOYMENT_PHASE=.*|TRADING_DEPLOYMENT_PHASE=micro|' "$HIBS_ROOT/.env"
  else
    echo "TRADING_DEPLOYMENT_PHASE=micro" >> "$HIBS_ROOT/.env"
  fi
  systemctl restart hibs-bet 2>/dev/null || true
fi

if [[ "$START_UNITS" -eq 1 ]]; then
  if systemctl is-active --quiet trading-paper 2>/dev/null; then
    log "Stopping trading-paper (9109) — micro replaces active submit lane"
    run systemctl stop trading-paper || true
  fi
  run systemctl enable trading-micro
  run systemctl start trading-micro
  log "Started trading-micro (metrics :${METRICS_PORT})"
fi

cat <<EOF

Micro install complete.

  journalctl -u trading-micro -f
  curl -s http://127.0.0.1:${METRICS_PORT}/ready
  open https://hibs-bet.co.uk/harvested-execution

Caps: \$100/order · \$500 gross (enforced in gate_enforcer.py)

EOF
