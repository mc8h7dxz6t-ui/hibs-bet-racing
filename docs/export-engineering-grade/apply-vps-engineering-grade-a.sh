#!/usr/bin/env bash
# Engineering grade A + Inst++ automation baseline (one shot on VPS).
#
# Clears institutional_readiness warnings (auth, CLV, trial cohort, sharpen, calib cache)
# and arms crons for F3 / hands-off / watchdog. Evidence grade (F7–F9) still needs matchdays.
#
#   sudo bash /opt/hibs-bet/deploy/apply-vps-engineering-grade-a.sh
#   sudo bash /opt/hibs-bet/deploy/apply-vps-engineering-grade-a.sh --new-evidence-date
#   sudo bash /opt/hibs-bet/deploy/apply-vps-engineering-grade-a.sh --skip-calibration
#
# Prereq: code synced to /opt/hibs-bet (git pull or rsync). Auth password in .env if HIBS_AUTH_ENABLED=1.
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-bet}"
ENV_FILE="${APP_ROOT}/.env"
MARKER="# --- VPS engineering grade A (institutional controls) ---"
NEW_DATE=0
SKIP_CALIB=0

for arg in "$@"; do
  case "${arg}" in
    --new-evidence-date) NEW_DATE=1 ;;
    --skip-calibration) SKIP_CALIB=1 ;;
  esac
done

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

[[ -d "${APP_ROOT}/deploy" ]] || { echo "Missing ${APP_ROOT} — sync repo first." >&2; exit 1; }
touch "${ENV_FILE}"

step() { echo ""; echo "==> $*"; }

_preserved_hibs_awk='function preserved(line) {
  return line ~ /^HIBS_(SECRET_KEY|AUTH_PASSWORD|HIBS_PASSWORD|AUTH_USERNAME)=/
}'

strip_warning_flags() {
  local tmp
  tmp="$(mktemp)"
  grep -vE '^(HIBS_DEV_FULL_DQ=1|HIBS_FETCH_ALL_DOMESTIC=1)\s*$' "${ENV_FILE}" >"${tmp}" || true
  mv "${tmp}" "${ENV_FILE}"
}

upsert_engineering_block() {
  if grep -qF "${MARKER}" "${ENV_FILE}"; then
    tmp="$(mktemp)"
    awk -v m="${MARKER}" "${_preserved_hibs_awk}"'
      $0 == m { skip=1; next }
      skip && /^HIBS_/ && !preserved($0) { next }
      skip && /^$/ { skip=0; next }
      skip && /^[^#]/ { skip=0 }
      { print }
    ' "${ENV_FILE}" >"$tmp"
    mv "$tmp" "${ENV_FILE}"
  fi

  cat >>"${ENV_FILE}" <<EOF

${MARKER}
HIBS_PRODUCTION=1
HIBS_PREDICTION_LOG_ENABLED=1
HIBS_CLV_LOG_ENABLED=1
HIBS_AUDIT_ODDS_RETRY=1
HIBS_AUDIT_REQUIRE_ODDS=1
HIBS_AUTH_PUBLIC_HEALTH=1
HIBS_F9_TRIAL_LEAGUES_ONLY=1
HIBS_SHARPEN_GATES=1
HIBS_VALUE_LEAGUES=EPL,SCOTLAND,UCL,EUROPA_LEAGUE,UECL,LA_LIGA,SERIE_A,BUNDESLIGA,LIGUE_1,EREDIVISIE,PRIMEIRA
HIBS_CALIBRATION_CACHE=${APP_ROOT}/.cache/calibration_v1.json
EOF

  if ! grep -qE '^HIBS_EVIDENCE_DEPLOY_DATE=' "${ENV_FILE}"; then
    echo "HIBS_EVIDENCE_DEPLOY_DATE=$(date -u +%Y-%m-%d)" >>"${ENV_FILE}"
  elif [[ "${NEW_DATE}" -eq 1 ]]; then
    sed -i "s/^HIBS_EVIDENCE_DEPLOY_DATE=.*/HIBS_EVIDENCE_DEPLOY_DATE=$(date -u +%Y-%m-%d)/" "${ENV_FILE}"
  fi

  chown www-data:www-data "${ENV_FILE}"
  chmod 640 "${ENV_FILE}"
}

step "1/8 Strip dev-only flags that downgrade engineering grade"
strip_warning_flags

step "2/8 Production + trial + domestic evidence profiles"
if [[ -f "${APP_ROOT}/deploy/apply-vps-safe-production.sh" ]]; then
  bash "${APP_ROOT}/deploy/apply-vps-safe-production.sh"
fi
if [[ -f "${APP_ROOT}/deploy/apply-vps-trial-production.sh" ]]; then
  bash "${APP_ROOT}/deploy/apply-vps-trial-production.sh"
fi
domestic_args=()
[[ "${NEW_DATE}" -eq 1 ]] && domestic_args+=(--new-evidence-date)
if [[ -f "${APP_ROOT}/deploy/apply-vps-domestic-evidence.sh" ]]; then
  bash "${APP_ROOT}/deploy/apply-vps-domestic-evidence.sh" "${domestic_args[@]}"
fi

step "3/8 Engineering A env block (audit + trial cohort + evidence date)"
upsert_engineering_block

step "4/8 Inst++ automation (crons, hands-off, watchdog)"
if [[ -f "${APP_ROOT}/deploy/cron-hibs-ops-automation.sh" ]]; then
  bash "${APP_ROOT}/deploy/cron-hibs-ops-automation.sh" --install
fi
if [[ -f "${APP_ROOT}/scripts/install_hands_off_automation.sh" ]]; then
  bash "${APP_ROOT}/scripts/install_hands_off_automation.sh"
fi
if [[ -f "${APP_ROOT}/deploy/cron-hibs-institutional-watchdog.sh" ]]; then
  bash "${APP_ROOT}/deploy/cron-hibs-institutional-watchdog.sh" --install
fi
if [[ -f "${APP_ROOT}/deploy/cron-hibs-football-fixture-warm.sh" ]]; then
  bash "${APP_ROOT}/deploy/cron-hibs-football-fixture-warm.sh" --install
fi

step "5/8 www-data sudoers for cron (if installer present)"
if [[ -f "${APP_ROOT}/deploy/install-hibs-cron-sudoers.sh" ]]; then
  bash "${APP_ROOT}/deploy/install-hibs-cron-sudoers.sh" || true
fi

step "6/8 Calibration cache (best effort — needs scored audit rows)"
mkdir -p "${APP_ROOT}/.cache"
chown www-data:www-data "${APP_ROOT}/.cache"
PY="${APP_ROOT}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY=python3
if [[ "${SKIP_CALIB}" -eq 0 && -x "${PY}" ]]; then
  sudo -u www-data env HOME="${APP_ROOT}" PYTHONPATH="${APP_ROOT}/src" \
    "${PY}" -m hibs_predictor.main calibration-fit 2>/dev/null || \
    echo "    calibration-fit skipped (no scored rows yet — re-run after matchdays)"
fi

step "7/8 Restart hibs-bet (2 workers from safe-production)"
systemctl daemon-reload 2>/dev/null || true
systemctl restart hibs-bet
sleep 4
systemctl is-active hibs-bet

step "8/8 Grade report"
export HOME="${APP_ROOT}" PYTHONPATH="${APP_ROOT}/src"
sudo -u www-data env HOME="${APP_ROOT}" PYTHONPATH="${APP_ROOT}/src" \
  "${PY}" "${APP_ROOT}/scripts/validate_institutional_config.py" || true
if [[ -f "${APP_ROOT}/scripts/verify_engineering_grade_a.sh" ]]; then
  bash "${APP_ROOT}/scripts/verify_engineering_grade_a.sh" || true
fi
if [[ -f "${APP_ROOT}/scripts/verify_inst_pp_automation.sh" ]]; then
  bash "${APP_ROOT}/scripts/verify_inst_pp_automation.sh" || true
fi

cat <<EOF

========== Engineering grade A — applied ==========

Engineering A requires zero warnings in institutional_readiness:
  - HIBS_AUTH_ENABLED=1 + HIBS_SECRET_KEY + HIBS_AUTH_PASSWORD in .env
  - calibration_v1.json present (calibration-fit after scored rows)
  - no HIBS_FETCH_ALL_DOMESTIC / HIBS_DEV_FULL_DQ

Verify:
  curl -sS 'https://hibs-bet.co.uk/api/health?light=1' | python3 -c "
import json,sys; d=json.load(sys.stdin); ir=d.get('institutional_readiness') or {}
print('engineering:', ir.get('engineering_grade'))
print('evidence:', ir.get('evidence_grade'))
print('warnings:', ir.get('warnings'))
print('blocking:', ir.get('blocking_issues'))
"
  bash ${APP_ROOT}/scripts/verify_engineering_grade_a.sh
  bash ${APP_ROOT}/scripts/green_forward_evidence.sh

Evidence grade (institutional buyer_ready) needs calendar time:
  fixtures > 0 → snapshots → ≥3 matchdays → F7 capture ≥50% → CLV n≥25 → F9 beat-close ≥50%

EOF
