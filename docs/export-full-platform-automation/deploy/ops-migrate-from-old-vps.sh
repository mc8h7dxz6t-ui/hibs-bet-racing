#!/usr/bin/env bash
# Pull state from old split VPS stack onto consolidated box (87.106.100.52).
#
# Old layout (reference):
#   77.68.89.73 — football, racing, trading, nginx
#   77.68.89.75 — FVE / line shopper (:8010)
#
# Run on NEW VPS as root (SSH key to old hosts must work):
#   sudo OLD_MAIN=root@77.68.89.73 OLD_FVE=root@77.68.89.75 \
#     bash /opt/hibs-bet/deploy/ops-migrate-from-old-vps.sh
#
# Dry run:
#   sudo bash /opt/hibs-bet/deploy/ops-migrate-from-old-vps.sh --dry-run
#
# Skip FVE pull (if .75 unreachable):
#   sudo bash /opt/hibs-bet/deploy/ops-migrate-from-old-vps.sh --skip-fve
set -euo pipefail

OLD_MAIN="${OLD_MAIN:-root@77.68.89.73}"
OLD_FVE="${OLD_FVE:-root@77.68.89.75}"
NEW_APP="${DEPLOY_PATH:-/opt/hibs-bet}"
NEW_RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
NEW_TRADING="${TRADING_INSTALL_ROOT:-/opt/trading-core}"
NEW_FVE="${FVE_DEPLOY_PATH:-/opt/fve}"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_ROOT="/var/backups/hibs-migrate-${STAMP}"
DRY=0
SKIP_FVE=0
SKIP_TRADING=0

for arg in "$@"; do
  case "${arg}" in
    --dry-run) DRY=1 ;;
    --skip-fve) SKIP_FVE=1 ;;
    --skip-trading) SKIP_TRADING=1 ;;
    -h|--help)
      sed -n '2,18p' "$0"
      exit 0
      ;;
  esac
done

log() { echo "[migrate] $*"; }
warn() { echo "[migrate] WARN: $*" >&2; }
run() {
  if [[ "${DRY}" -eq 1 ]]; then
    echo "[dry-run] $*"
  else
    "$@"
  fi
}

[[ "$(id -u)" -eq 0 ]] || { echo "run as root on NEW VPS" >&2; exit 1; }

RSYNC=(rsync -a --partial --info=progress2)
SSH_OPTS=(-o BatchMode=yes -o ConnectTimeout=20 -o StrictHostKeyChecking=accept-new)

preflight_ssh() {
  local host="$1"
  if ! ssh "${SSH_OPTS[@]}" "${host}" "echo ok" >/dev/null 2>&1; then
    warn "cannot SSH to ${host} — fix keys or run rsync from Mac as jump host"
    return 1
  fi
  return 0
}

remote_path_exists() {
  local host="$1" path="$2"
  ssh "${SSH_OPTS[@]}" "${host}" "test -e '${path}'" 2>/dev/null
}

pull_rsync() {
  local host="$1" remote="$2" local="$3"
  shift 3
  local extra=("$@")
  mkdir -p "${local}"
  log "pull ${host}:${remote} -> ${local}"
  run "${RSYNC[@]}" "${extra[@]}" -e "ssh ${SSH_OPTS[*]}" "${host}:${remote}" "${local}"
}

step() { echo ""; echo "========== $* =========="; }

step "0) Preflight SSH"
preflight_ssh "${OLD_MAIN}" || exit 1
if [[ "${SKIP_FVE}" -eq 0 ]]; then
  preflight_ssh "${OLD_FVE}" || warn "FVE host unreachable — use --skip-fve"
fi

step "1) Backup NEW state before overwrite"
run mkdir -p "${BACKUP_ROOT}"
for item in "${NEW_APP}/.env" "${NEW_RACING}/.env" /etc/trading_secrets; do
  if [[ -f "${item}" ]]; then
    run cp -a "${item}" "${BACKUP_ROOT}/" 2>/dev/null || true
  fi
done
log "backup at ${BACKUP_ROOT}"

step "2) Football — /opt/hibs-bet (.env, cache, data, state)"
mkdir -p "${NEW_APP}/.cache" "${NEW_APP}/data"
if remote_path_exists "${OLD_MAIN}" "/opt/hibs-bet/.env"; then
  pull_rsync "${OLD_MAIN}" "/opt/hibs-bet/.env" "${NEW_APP}/.env"
  run chown www-data:www-data "${NEW_APP}/.env"
  run chmod 640 "${NEW_APP}/.env"
else
  warn "no .env on old main"
fi
pull_rsync "${OLD_MAIN}" "/opt/hibs-bet/.cache/" "${NEW_APP}/.cache/" 2>/dev/null || warn "cache pull failed"
pull_rsync "${OLD_MAIN}" "/opt/hibs-bet/data/" "${NEW_APP}/data/" \
  --exclude '__pycache__' 2>/dev/null || warn "data pull failed"
for f in .rate_limit_state.json .deploy-revision; do
  if remote_path_exists "${OLD_MAIN}" "/opt/hibs-bet/${f}"; then
    pull_rsync "${OLD_MAIN}" "/opt/hibs-bet/${f}" "${NEW_APP}/${f}"
  fi
done
run chown -R www-data:www-data "${NEW_APP}/.cache" "${NEW_APP}/data" 2>/dev/null || true

step "3) Racing — /opt/hibs-racing + block volume"
mkdir -p "${NEW_RACING}/data"
if remote_path_exists "${OLD_MAIN}" "/opt/hibs-racing/.env"; then
  pull_rsync "${OLD_MAIN}" "/opt/hibs-racing/.env" "${NEW_RACING}/.env"
fi
pull_rsync "${OLD_MAIN}" "/opt/hibs-racing/data/" "${NEW_RACING}/data/" 2>/dev/null || warn "racing data pull failed"
if remote_path_exists "${OLD_MAIN}" "/mnt/hibs-racing-data/"; then
  mkdir -p /mnt/hibs-racing-data
  pull_rsync "${OLD_MAIN}" "/mnt/hibs-racing-data/" "/mnt/hibs-racing-data/" 2>/dev/null || true
fi
run chown -R www-data:www-data "${NEW_RACING}" 2>/dev/null || true

step "4) Trading — /opt/trading-core data + /etc/trading_secrets"
if [[ "${SKIP_TRADING}" -eq 0 ]]; then
  mkdir -p "${NEW_TRADING}/data"
  if remote_path_exists "${OLD_MAIN}" "/opt/trading-core/data/"; then
    pull_rsync "${OLD_MAIN}" "/opt/trading-core/data/" "${NEW_TRADING}/data/" 2>/dev/null || warn "trading data pull failed"
  fi
  if remote_path_exists "${OLD_MAIN}" "/etc/trading_secrets"; then
  run cp -a /etc/trading_secrets "/etc/trading_secrets.bak.${STAMP}" 2>/dev/null || true
    pull_rsync "${OLD_MAIN}" "/etc/trading_secrets" "/etc/trading_secrets"
    run chmod 600 /etc/trading_secrets
  fi
fi

step "5) FVE — scrape-lines + docker env from old .75"
if [[ "${SKIP_FVE}" -eq 0 ]] && preflight_ssh "${OLD_FVE}"; then
  mkdir -p /var/lib/fve/scrape-lines "${NEW_FVE}"
  for remote in \
    "/var/lib/fve/scrape-lines/" \
    "/mnt/fve-data/scrape-lines/" \
    "/opt/football-app/scrape-lines/" \
    "/opt/fve/scrape-lines/"; do
    if remote_path_exists "${OLD_FVE}" "${remote}"; then
      pull_rsync "${OLD_FVE}" "${remote}" "/var/lib/fve/scrape-lines/" 2>/dev/null && break
    fi
  done
  for envpath in /opt/football-app/.env /opt/fve/.env; do
    if remote_path_exists "${OLD_FVE}" "${envpath}"; then
      pull_rsync "${OLD_FVE}" "${envpath}" "${NEW_FVE}/.env.migrated"
      break
    fi
  done
fi

step "6) www-data crontab from old main (optional)"
if [[ "${DRY}" -eq 0 ]]; then
  ssh "${SSH_OPTS[@]}" "${OLD_MAIN}" "crontab -u www-data -l 2>/dev/null" \
    >"${BACKUP_ROOT}/www-data.crontab.from-old" 2>/dev/null || warn "no www-data crontab on old"
  log "saved old crontab to ${BACKUP_ROOT}/www-data.crontab.from-old"
  log "re-install crons on new with: bash ${NEW_APP}/scripts/install_hands_off_automation.sh"
fi

step "7) Consolidated stack.env (FVE local on new box)"
mkdir -p /etc/hibs-bet
cat >/etc/hibs-bet/stack.env <<EOF
FVE_REMOTE_HOST=127.0.0.1
HIBS_PUBLIC_HOST=hibs-bet.co.uk
HIBS_VPS_IP=87.106.100.52
EOF

step "8) Patch .env for consolidated host"
if [[ -f "${NEW_APP}/.env" && "${DRY}" -eq 0 ]]; then
  for kv in \
    "FVE_API_URL=http://127.0.0.1:8010" \
    "HIBS_FVE_INTEGRATION=1" \
    "FVE_REMOTE_HOST=127.0.0.1"; do
    k="${kv%%=*}"
    if grep -q "^${k}=" "${NEW_APP}/.env"; then
      sed -i "s|^${k}=.*|${kv}|" "${NEW_APP}/.env"
    else
      echo "${kv}" >>"${NEW_APP}/.env"
    fi
  done
  sed -i 's|FVE_API_URL=.*77\.68\.89\.75.*|FVE_API_URL=http://127.0.0.1:8010|g' "${NEW_APP}/.env" 2>/dev/null || true
  chown www-data:www-data "${NEW_APP}/.env"
fi

step "9) Wire + restart"
if [[ "${DRY}" -eq 0 ]]; then
  [[ -f "${NEW_APP}/deploy/ensure-vps-stack-wiring.sh" ]] && \
    bash "${NEW_APP}/deploy/ensure-vps-stack-wiring.sh" --repair || true
  [[ -f "${NEW_APP}/scripts/install_hands_off_automation.sh" ]] && \
    bash "${NEW_APP}/scripts/install_hands_off_automation.sh" || true
  systemctl restart hibs-bet 2>/dev/null || true
  systemctl restart hibs-racing 2>/dev/null || true
  systemctl restart trading-shadow-soak 2>/dev/null || true
  sleep 4
fi

step "10) Verify"
if [[ "${DRY}" -eq 0 ]]; then
  curl -fsS --max-time 15 http://127.0.0.1:8000/api/ping 2>/dev/null | head -c 400 || warn "football ping failed"
  echo ""
  cd "${NEW_APP}" && python3 -c "
from pathlib import Path
from dotenv import load_dotenv
import os, glob
load_dotenv('.env')
v = (os.getenv('FOOTBALL_DATA_ORG_KEY') or '').strip()
print('FOOTBALL_DATA_ORG_KEY:', 'OK' if len(v)>=8 else 'MISSING')
bundles = glob.glob('.cache/all_fixtures*.json')
print('fixture bundles:', len(bundles), '(files)' if bundles else 'NONE')
db = Path('data/prediction_audit.sqlite')
print('audit db:', f'{db.stat().st_size//1024}KB' if db.is_file() else 'MISSING')
" 2>/dev/null || true
fi

cat <<EOF

========== MIGRATION COMPLETE ==========
Backup of NEW pre-migrate files: ${BACKUP_ROOT}

If SSH from new->old failed, run the same rsync FROM YOUR MAC:
  rsync -avz -e ssh root@77.68.89.73:/opt/hibs-bet/.env root@87.106.100.52:/opt/hibs-bet/
  rsync -avz -e ssh root@77.68.89.73:/opt/hibs-bet/.cache/ root@87.106.100.52:/opt/hibs-bet/.cache/
  rsync -avz -e ssh root@77.68.89.73:/opt/hibs-bet/data/ root@87.106.100.52:/opt/hibs-bet/data/

Then on NEW:
  sudo chown -R www-data:www-data /opt/hibs-bet/.env /opt/hibs-bet/.cache /opt/hibs-bet/data
  sudo systemctl restart hibs-bet hibs-racing

Public check:
  curl -sS https://www.hibs-bet.co.uk/api/ping | python3 -m json.tool
EOF
