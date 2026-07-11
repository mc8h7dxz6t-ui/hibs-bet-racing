#!/usr/bin/env bash
# Ordered full-stack recovery — football, racing, FVE, UI cross-links, automation arm.
#
# Industry on-call entry point when public 502 or hands-off automation is unarmed.
#
#   sudo bash /opt/hibs-bet/scripts/vps_full_stack_recovery.sh
#   sudo bash /opt/hibs-bet/scripts/vps_full_stack_recovery.sh --arm-only
#   sudo bash /opt/hibs-bet/scripts/vps_full_stack_recovery.sh --skip-fve
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
LOG_DIR="${LOG_DIR:-/var/log/hibs-bet}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
ARM_ONLY=0
SKIP_FVE=0
SKIP_ARM=0

for arg in "$@"; do
  case "${arg}" in
    --arm-only) ARM_ONLY=1 ;;
    --skip-fve) SKIP_FVE=1 ;;
    --skip-arm) SKIP_ARM=1 ;;
  esac
done

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
mkdir -p "${LOG_DIR}"

if [[ -f /etc/hibs-bet/stack.env ]]; then
  # shellcheck disable=SC1091
  source /etc/hibs-bet/stack.env
  PUBLIC="${HIBS_PUBLIC_HOST:-${PUBLIC}}"
fi
FVE_HOST="${FVE_REMOTE_HOST:-127.0.0.1}"

log() { echo "[full-recovery] $*"; }
warn() { echo "[full-recovery] WARN: $*" >&2; }
step() { echo ""; log "===== $* ====="; }

export DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}" HIBS_PUBLIC_HOST="${PUBLIC}"

step "0) preflight"
free -h | head -2 | sed 's/^/    /' || true
if [[ -f "${APP}/scripts/verify_vps_relative_paths.sh" ]]; then
  bash "${APP}/scripts/verify_vps_relative_paths.sh" || warn "drift — sync overlay or scp scripts from Mac"
else
  warn "missing verify_vps_relative_paths.sh — overlay not synced"
fi

if [[ "${ARM_ONLY}" -eq 1 ]]; then
  step "arm-only — skip service repair"
else
  step "1) crontab emergency (if bloated)"
  if [[ -f "${APP}/deploy/lib_cron_dedupe.sh" ]]; then
    # shellcheck source=../deploy/lib_cron_dedupe.sh
    source "${APP}/deploy/lib_cron_dedupe.sh"
    cron_n="$(hibs_crontab_line_count www-data 2>/dev/null || echo 0)"
    if [[ "${cron_n}" -gt "${HIBS_CRON_MAX_LINES:-200}" ]] && \
       [[ -f "${APP}/deploy/crontab-emergency-sports-only.sh" ]]; then
      warn "www-data crontab ${cron_n} lines — emergency sports-only"
      bash "${APP}/deploy/crontab-emergency-sports-only.sh" || true
    fi
  fi

  step "2) UI overlay + dashboard filters"
  if [[ -f "${APP}/scripts/vps_football_apply_embedded_overlay.sh" ]]; then
    bash "${APP}/scripts/vps_football_apply_embedded_overlay.sh" || warn "embedded overlay partial"
  elif [[ -f "${APP}/scripts/vps_football_fix_dashboard_500.sh" ]]; then
    bash "${APP}/scripts/vps_football_fix_dashboard_500.sh" || warn "dashboard fix partial"
  fi

  step "3) football hard recovery (502 / :8000)"
  if [[ -f "${APP}/scripts/vps_football_hard_recovery.sh" ]]; then
    bash "${APP}/scripts/vps_football_hard_recovery.sh" || warn "football recovery incomplete"
  else
    warn "missing vps_football_hard_recovery.sh"
  fi

  step "4) nginx production + racing proxy + cross-links"
  if [[ -f "${APP}/scripts/vps_football_ensure_nginx_production.sh" ]]; then
    bash "${APP}/scripts/vps_football_ensure_nginx_production.sh" || warn "nginx ensure issues"
  fi
  if [[ -f "${APP}/deploy/apply-vps-site-cross-links.sh" ]]; then
    CROSS_LINK_RACING=auto CROSS_LINK_PUBLIC=path \
      bash "${APP}/deploy/apply-vps-site-cross-links.sh" || true
  fi
  systemctl restart hibs-bet 2>/dev/null || true
  sleep 4

  step "5) racing hard recovery (if :5003 not green)"
  rc_ping="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 http://127.0.0.1:5003/api/ping 2>/dev/null || echo 000)"
  log "racing localhost ping=${rc_ping}"
  if [[ "${rc_ping}" != "200" && -f "${APP}/scripts/vps_racing_hard_recovery.sh" ]]; then
    HIBS_BET_DEPLOY_PATH="${APP}" HIBS_RACING_DEPLOY_PATH="${RACING}" \
      bash "${APP}/scripts/vps_racing_hard_recovery.sh" || warn "racing recovery incomplete"
  fi

  if [[ "${SKIP_FVE}" -eq 0 ]]; then
    step "6) FVE / line-trader"
    case "${FVE_HOST}" in
      127.0.0.1|localhost|::1)
        if [[ -f "${APP}/scripts/lib_fve_local_repair.sh" ]]; then
          bash "${APP}/scripts/lib_fve_local_repair.sh" || warn "local FVE repair issues"
        fi
        ;;
      *)
        if [[ -f "${APP}/deploy/apply-vps-fve-remote-host.sh" ]]; then
          FVE_REMOTE_HOST="${FVE_HOST}" HIBS_PUBLIC_HOST="${PUBLIC}" \
            bash "${APP}/deploy/apply-vps-fve-remote-host.sh" || warn "remote FVE wire issues"
        fi
        ;;
    esac
  else
    log "skip FVE (--skip-fve)"
  fi

  step "7) stack wiring"
  if [[ -f "${APP}/deploy/ensure-vps-stack-wiring.sh" ]]; then
    bash "${APP}/deploy/ensure-vps-stack-wiring.sh" --repair || true
  fi

  step "8) trading (status only — usually parked)"
  if [[ -d "${TRADING}" ]]; then
    if systemctl is-active --quiet trading-shadow-soak 2>/dev/null; then
      log "trading-shadow-soak active"
    else
      log "trading-shadow-soak inactive (expected if Day-15 FAIL / hard stop)"
    fi
  fi
fi

if [[ "${SKIP_ARM}" -eq 0 ]]; then
  step "9) arm hands-off automation"
  if [[ -f "${APP}/deploy/install-hibs-cron-sudoers.sh" ]]; then
    bash "${APP}/deploy/install-hibs-cron-sudoers.sh" || warn "sudoers install issues"
  fi
  if [[ -f "${APP}/deploy/cron-hibs-infra-fallback.sh" ]]; then
    bash "${APP}/deploy/cron-hibs-infra-fallback.sh" --install || warn "infra fallback cron not installed"
  fi
  if [[ -f "${APP}/deploy/cron-hibs-ops-automation.sh" ]]; then
    bash "${APP}/deploy/cron-hibs-ops-automation.sh" --install || warn "ops automation install issues"
  fi
fi

step "10) verify"
if [[ -f "${APP}/scripts/verify_public_edge.sh" ]]; then
  bash "${APP}/scripts/verify_public_edge.sh" || warn "public edge not fully green"
fi
if [[ -f "${APP}/scripts/vps_industry_standard_run.sh" ]]; then
  bash "${APP}/scripts/vps_industry_standard_run.sh" --repair || warn "industry run exit non-zero (evidence red OK off-season)"
fi

log "DONE — check /var/log/hibs-bet/three-stack-status.json"
log "open https://${PUBLIC}/ https://${PUBLIC}/racing/cards https://${PUBLIC}/line-trader"
