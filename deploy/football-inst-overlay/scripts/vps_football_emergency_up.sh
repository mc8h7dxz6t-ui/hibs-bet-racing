#!/usr/bin/env bash
# Emergency: diagnose + apply embedded overlay + get hibs-bet / back to 200.
#
#   sudo bash /opt/hibs-bet/scripts/vps_football_emergency_up.sh
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
LOG="${BET}/logs/hibs-bet.log"

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
[[ -d "${BET}" ]] || { echo "missing ${BET}" >&2; exit 1; }

echo "==> vps_football_emergency_up $(date -u +%Y-%m-%dT%H:%M:%SZ)"
echo "    bet=${BET}"

echo ""
echo "==> diagnose"
systemctl is-active hibs-bet 2>/dev/null || echo "hibs-bet inactive"
free -h | head -2 | sed 's/^/    /'
curl -sS -o /dev/null -w '    ping=%{http_code}\n' --max-time 8 http://127.0.0.1:8000/api/ping 2>/dev/null || echo "    ping=000"
curl -sS -o /dev/null -w '    root=%{http_code}\n' --max-time 12 http://127.0.0.1:8000/ 2>/dev/null || echo "    root=000"

REQUIRED=(
  _hibs_brand.html _launch_wait_overlay.html _portfolio_bar.html _product_switcher.html
  _term_hint.html _site_ops_chips.html _inst_grade_chip.html _players_dock.html
  _betslip_drawer.html _fixture_row_compact.html _dashboard_logged_results.html
  _dashboard_recent_results.html _betting_guide.html _assistant_widget.html
  _football_site_nav.html login.html
)
missing=()
for f in "${REQUIRED[@]}"; do
  [[ -f "${BET}/templates/${f}" ]] || missing+=("${f}")
done
if [[ ${#missing[@]} -gt 0 ]]; then
  echo "    MISSING templates: ${missing[*]}"
else
  echo "    templates: all ${#REQUIRED[@]} present"
fi
if [[ -f "${BET}/templates/_fixture_row_compact.html" ]] && grep -q expand_panel "${BET}/templates/_fixture_row_compact.html" 2>/dev/null; then
  echo "    WARN: _fixture_row_compact still includes expand panel"
fi
if [[ -f "${LOG}" ]]; then
  echo "    last error:"
  tail -8 "${LOG}" | grep -E 'ERROR|Template|Traceback|File "' | tail -5 | sed 's/^/      /' || true
fi

echo ""
echo "==> apply embedded overlay"
EMBED="${BET}/scripts/vps_football_apply_embedded_overlay.sh"
if [[ ! -f "${EMBED}" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  EMBED="${SCRIPT_DIR}/vps_football_apply_embedded_overlay.sh"
fi
if [[ ! -f "${EMBED}" ]]; then
  echo "ERROR: missing vps_football_apply_embedded_overlay.sh" >&2
  echo "Copy from repo: deploy/football-inst-overlay/scripts/vps_football_apply_embedded_overlay.sh" >&2
  exit 1
fi
bash "${EMBED}"

echo ""
echo "==> auth off + lite mode"
touch "${BET}/.env"
grep -q '^HIBS_AUTH_ENABLED=' "${BET}/.env" && sed -i 's/^HIBS_AUTH_ENABLED=.*/HIBS_AUTH_ENABLED=0/' "${BET}/.env" || echo 'HIBS_AUTH_ENABLED=0' >>"${BET}/.env"
grep -q '^HIBS_DASHBOARD_LITE=' "${BET}/.env" || echo 'HIBS_DASHBOARD_LITE=1' >>"${BET}/.env"
grep -q '^HIBS_PROGRESSIVE_LOAD=' "${BET}/.env" || echo 'HIBS_PROGRESSIVE_LOAD=1' >>"${BET}/.env"
chown www-data:www-data "${BET}/.env"

mkdir -p /etc/systemd/system/hibs-bet.service.d
cat >/etc/systemd/system/hibs-bet.service.d/pressure-relief.conf <<EOF
[Service]
ExecStart=
ExecStart=${BET}/.venv/bin/gunicorn --workers 1 --bind 0.0.0.0:8000 --timeout 180 --graceful-timeout 30 --access-logfile - --error-logfile - hibs_predictor.web:app
EOF
systemctl daemon-reload
systemctl restart hibs-bet
sleep 6

echo ""
echo "==> verify (3 tries)"
ok=0
for i in 1 2 3; do
  ping_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 10 http://127.0.0.1:8000/api/ping 2>/dev/null || echo 000)"
  root_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 15 http://127.0.0.1:8000/ 2>/dev/null || echo 000)"
  echo "    try${i}: ping=${ping_code} root=${root_code}"
  [[ "${ping_code}" == "200" && "${root_code}" =~ ^(200|302)$ ]] && ok=1
  sleep 2
done

if [[ "${ok}" -eq 1 ]]; then
  echo ""
  echo "GREEN: hibs-bet up"
  exit 0
fi

echo ""
echo "RED: still failing"
tail -20 "${LOG}" 2>/dev/null | sed 's/^/  /' || journalctl -u hibs-bet -n 20 --no-pager
exit 1
