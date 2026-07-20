#!/usr/bin/env bash
# Sync exchange-ev branch onto /opt/hibs-racing when the tree is not a git clone.
#
#   sudo bash /opt/hibs-racing/deploy/vps-pull-exchange-ev.sh
#
# Requires: git + network + read access to origin (deploy key or HTTPS token on VPS).
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-racing}"
BRANCH="${BRANCH:-cursor/exchange-place-ev-kelly-12e0}"
REMOTE="${REMOTE:-https://github.com/mc8h7dxz6t-ui/hibs-bet-racing.git}"

cd "${APP_ROOT}"

if [[ ! -d .git ]]; then
  echo "==> Initializing git in ${APP_ROOT}"
  git init
  git remote add origin "${REMOTE}" 2>/dev/null || git remote set-url origin "${REMOTE}"
fi

echo "==> Fetch ${BRANCH}"
git fetch origin "${BRANCH}"
git checkout -B "${BRANCH}" "origin/${BRANCH}"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install -e ".[dev,ranker,web]" -q

echo "==> Apply shadow env profile"
bash "${APP_ROOT}/deploy/apply-vps-exchange-ev.sh"

echo "GREEN: branch ${BRANCH} checked out. Next:"
echo "  cd ${APP_ROOT} && source .venv/bin/activate && set -a && source .env && set +a"
echo "  hibs-racing score-card --odds-source matchbook"
echo "  hibs-racing exchange-ev-status"
echo "  sudo systemctl restart hibs-racing"
