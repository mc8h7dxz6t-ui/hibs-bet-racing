#!/usr/bin/env bash
# Bootstrap FVE + line ingest on a dedicated ~1GB VPS (football-app /opt/fve).
#
# Line-trader HTML stays on the main hibs-bet host; this box runs Redis + API + worker only.
#
# On the 1GB VPS (e.g. 77.68.89.75):
#   curl -fsSL https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet/cursor/three-platform-inst-prime-c6a1/deploy/bootstrap-fve-dedicated-1gb.sh | sudo \
#     HIBS_UPSTREAM_BASE_URL=https://hibs-bet.co.uk \
#     HIBS_MAIN_IP=87.106.100.52 \
#     bash
#
# Or from a synced repo:
#   sudo HIBS_MAIN_IP=87.106.100.52 bash /opt/hibs-bet/deploy/bootstrap-fve-dedicated-1gb.sh
set -euo pipefail

FVE_ROOT="${FVE_DEPLOY_PATH:-/opt/fve}"
FVE_PORT="${FVE_API_PORT:-8010}"
HIBS_URL="${HIBS_UPSTREAM_BASE_URL:-https://hibs-bet.co.uk}"
HIBS_MAIN_IP="${HIBS_MAIN_IP:-}"
SCRAPE_DIR="${FVE_SCRAPE_LINES_DIR:-/var/lib/fve/scrape-lines}"
BRANCH="${HIBS_FVE_RAW_BRANCH:-main}"
REPO="${FVE_GIT_REPO:-https://github.com/mc8h7dxz6t-ui/football-app.git}"
SWAP_MB="${FVE_SWAP_MB:-1024}"
VOLUME_DEVICE="${VOLUME_DEVICE:-}"
DOCKER_DATA="${DOCKER_DATA:-/var/lib/docker}"

log() { echo "[fve-1gb] $*"; }

mount_block_volume() {
  local mount_point="$1"
  [[ -n "${VOLUME_DEVICE}" ]] || return 0
  [[ -b "${VOLUME_DEVICE}" ]] || { log "ERROR: ${VOLUME_DEVICE} not found"; exit 1; }
  mkdir -p "${mount_point}"
  if ! blkid "${VOLUME_DEVICE}" >/dev/null 2>&1; then
    log "formatting ${VOLUME_DEVICE} ext4"
    mkfs.ext4 -F -L hibs-fve-data "${VOLUME_DEVICE}"
  fi
  if ! mountpoint -q "${mount_point}"; then
    mount "${VOLUME_DEVICE}" "${mount_point}"
  fi
  local uuid
  uuid="$(blkid -s UUID -o value "${VOLUME_DEVICE}")"
  grep -qF "${mount_point}" /etc/fstab 2>/dev/null || \
    echo "UUID=${uuid} ${mount_point} ext4 defaults,nofail 0 2" >> /etc/fstab
}

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

log "1/9 — swap (${SWAP_MB}MB) for 1GB RAM headroom"
if ! swapon --show | grep -q .; then
  if [[ ! -f /swapfile ]]; then
    fallocate -l "${SWAP_MB}M" /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count="${SWAP_MB}" status=none
    chmod 600 /swapfile
    mkswap /swapfile
  fi
  swapon /swapfile
  grep -q '^/swapfile' /etc/fstab 2>/dev/null || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  sysctl -w vm.swappiness=10 >/dev/null
  grep -q '^vm.swappiness=' /etc/sysctl.conf 2>/dev/null || echo 'vm.swappiness=10' >> /etc/sysctl.conf
  log "swap enabled"
else
  log "swap already active"
fi

log "2/9 — block storage (optional)"
if [[ -n "${VOLUME_DEVICE}" ]]; then
  mount_block_volume /mnt/fve-data
  if [[ -d "${DOCKER_DATA}" && ! -L "${DOCKER_DATA}" ]]; then
    systemctl stop docker 2>/dev/null || true
    mkdir -p /mnt/fve-data/docker
    rsync -a "${DOCKER_DATA}/" /mnt/fve-data/docker/ 2>/dev/null || true
    mv "${DOCKER_DATA}" "${DOCKER_DATA}.pre-volume.bak" 2>/dev/null || true
    ln -sfn /mnt/fve-data/docker "${DOCKER_DATA}"
    systemctl start docker 2>/dev/null || true
  fi
  mkdir -p /mnt/fve-data/fve-scrape
  SCRAPE_DIR=/mnt/fve-data/fve-scrape
fi

log "3/9 — docker"
if ! command -v docker >/dev/null 2>&1; then
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ca-certificates curl git
  curl -fsSL https://get.docker.com | sh
fi
systemctl enable --now docker 2>/dev/null || true

log "4/9 — FVE tree at ${FVE_ROOT}"
mkdir -p "${FVE_ROOT}" "${SCRAPE_DIR}" /var/log/fve
if [[ -d "${FVE_ROOT}/.git" ]]; then
  git -C "${FVE_ROOT}" fetch --depth 1 origin "${BRANCH}" 2>/dev/null && \
    git -C "${FVE_ROOT}" checkout "${BRANCH}" 2>/dev/null && \
    git -C "${FVE_ROOT}" pull --ff-only origin "${BRANCH}" 2>/dev/null || true
elif command -v git >/dev/null 2>&1; then
  git clone --depth 1 --branch "${BRANCH}" "${REPO}" "${FVE_ROOT}" 2>/dev/null || \
    git clone --depth 1 "${REPO}" "${FVE_ROOT}"
else
  log "ERROR: git required" >&2
  exit 1
fi

log "4/9 — minimal scrape .env (no postgres / streamlit)"
ENV_FILE="${FVE_ROOT}/.env"
touch "${ENV_FILE}"
upsert() {
  local key="$1" val="$2"
  if grep -q "^${key}=" "${ENV_FILE}" 2>/dev/null; then
    sed -i "s|^${key}=.*|${key}=${val}|" "${ENV_FILE}"
  else
    echo "${key}=${val}" >> "${ENV_FILE}"
  fi
}
upsert FVE_PAUSED 0
upsert FVE_FEED_MODE scrape
upsert FVE_SCRAPE_HEAVY 1
upsert FVE_SCRAPE_LINES_DIR "${SCRAPE_DIR}"
upsert HIBS_UPSTREAM_BASE_URL "${HIBS_URL}"
upsert FVE_AUTO_WATCHLIST 1
upsert FVE_API_PORT "${FVE_PORT}"
upsert FVE_WS_DELTA_UPDATES 1
upsert FVE_WS_CLIENT_DELTA 0
upsert WS_MAX_PENDING_SENDS 6
upsert FEED_POLL_SEC_MATCHBOOK 1.0
upsert FVE_MATCHBOOK_MAX_CALLS_PER_HOUR 30
upsert FVE_ODDS_API_MAX_CALLS_PER_HOUR 10
upsert FVE_API_FOOTBALL_MAX_CALLS_PER_HOUR 10
if [[ -n "${HIBS_UPSTREAM_TOKEN:-}" ]]; then
  upsert HIBS_UPSTREAM_TOKEN "${HIBS_UPSTREAM_TOKEN}"
fi

log "5/9 — docker memory caps (1GB host)"
OVERRIDE="${FVE_ROOT}/docker-compose.1gb.yml"
cat >"${OVERRIDE}" <<'YAML'
# Auto-generated for 1GB FVE host — redis + api + worker only.
services:
  redis:
    mem_limit: 96m
    cpus: 0.25
  api:
    mem_limit: 280m
    cpus: 0.50
  worker:
    mem_limit: 420m
    cpus: 0.75
YAML

log "6/9 — start redis + api + worker"
(
  cd "${FVE_ROOT}"
  FVE_API_PORT="${FVE_PORT}" COMPOSE_PROFILES=ingest \
    docker compose -f docker-compose.yml -f docker-compose.1gb.yml \
    up -d --build redis api worker
)

log "7/9 — firewall :${FVE_PORT} (main hibs host only)"
if command -v ufw >/dev/null 2>&1; then
  ufw --force enable 2>/dev/null || true
  ufw allow OpenSSH 2>/dev/null || ufw allow 22/tcp 2>/dev/null || true
  if [[ -n "${HIBS_MAIN_IP}" ]]; then
    ufw delete allow "${FVE_PORT}/tcp" 2>/dev/null || true
    ufw allow from "${HIBS_MAIN_IP}" to any port "${FVE_PORT}" proto tcp
    log "ufw: ${FVE_PORT} from ${HIBS_MAIN_IP} only"
  else
    ufw allow "${FVE_PORT}/tcp" 2>/dev/null || true
    log "WARN HIBS_MAIN_IP unset — ${FVE_PORT} open to world; set HIBS_MAIN_IP and re-run"
  fi
fi

log "8/9 — lines collector cron (5 min)"
TOKEN_ENV=""
if [[ -n "${HIBS_UPSTREAM_TOKEN:-}" ]]; then
  TOKEN_ENV="HIBS_UPSTREAM_TOKEN=${HIBS_UPSTREAM_TOKEN}"
fi
CRON_LINE="*/5 * * * * cd ${FVE_ROOT} && HIBS_UPSTREAM_BASE_URL=${HIBS_URL} FVE_SCRAPE_LINES_DIR=${SCRAPE_DIR} ${TOKEN_ENV} /usr/bin/python3 scripts/fve_hibs_lines_collector.py --from-watchlist >> /var/log/fve/lines-collector.log 2>&1"
( crontab -l 2>/dev/null | grep -v 'fve_hibs_lines_collector' || true; echo "${CRON_LINE}" ) | crontab -

if [[ -f "${FVE_ROOT}/scripts/fve_hibs_lines_collector.py" ]]; then
  (cd "${FVE_ROOT}" && HIBS_UPSTREAM_BASE_URL="${HIBS_URL}" FVE_SCRAPE_LINES_DIR="${SCRAPE_DIR}" ${TOKEN_ENV} \
    python3 scripts/fve_hibs_lines_collector.py --from-watchlist) || true
fi

sleep 5
if curl -fsS --max-time 10 "http://127.0.0.1:${FVE_PORT}/health" >/dev/null 2>&1; then
  log "FVE health OK on :${FVE_PORT}"
else
  log "WARN health not ready — check: cd ${FVE_ROOT} && docker compose logs --tail=40 worker"
fi

log "done — on MAIN hibs VPS run:"
echo "  sudo HIBS_MAIN_IP=87.106.100.52 FVE_REMOTE_HOST=$(hostname -I | awk '{print $1}') \\"
echo "    bash /opt/hibs-bet/deploy/apply-vps-fve-remote-host.sh"
echo ""
echo "verify from main:"
echo "  curl -sS http://$(hostname -I | awk '{print $1}'):${FVE_PORT}/health | head -c 400"
