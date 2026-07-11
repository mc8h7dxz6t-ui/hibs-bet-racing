#!/usr/bin/env bash
# Sync football overlay templates onto /opt/hibs-bet — no git on VPS required.
#
#   sudo bash /opt/hibs-bet/scripts/vps_football_sync_overlay_templates.sh
#   sudo GITHUB_OVERLAY_REF=cursor/fix-login-500-b3fc bash .../vps_football_sync_overlay_templates.sh
set -euo pipefail

BET="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
GITHUB_REPO="${GITHUB_OVERLAY_REPO:-mc8h7dxz6t-ui/hibs-bet-racing}"
GITHUB_REF="${GITHUB_OVERLAY_REF:-cursor/fix-login-500-b3fc}"
GITHUB_BASE="https://raw.githubusercontent.com/${GITHUB_REPO}/${GITHUB_REF}/deploy/football-inst-overlay"

TEMPLATES=(
  _hibs_brand.html
  _launch_wait_overlay.html
  _portfolio_bar.html
  _term_hint.html
  _site_ops_chips.html
  _inst_grade_chip.html
  _players_dock.html
  _betslip_drawer.html
  _fixture_row_compact.html
  _dashboard_logged_results.html
  _dashboard_recent_results.html
  _betting_guide.html
  _assistant_widget.html
  _football_site_nav.html
  login.html
)

log() { echo "[overlay-sync] $*"; }

[[ "$(id -u)" -eq 0 ]] || { echo "run as root: sudo bash $0" >&2; exit 1; }
[[ -d "${BET}/templates" ]] || { echo "missing ${BET}/templates" >&2; exit 1; }

resolve_overlay() {
  local candidate=""
  if [[ -n "${OVERLAY_ROOT:-}" && -d "${OVERLAY_ROOT}/templates" ]]; then
    echo "${OVERLAY_ROOT}"
    return 0
  fi
  for candidate in \
    "${BET}/deploy/football-inst-overlay" \
    "${RACING}/deploy/football-inst-overlay" \
    "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"; do
    [[ -n "${candidate}" && -d "${candidate}/templates" ]] || continue
    echo "${candidate}"
    return 0
  done
  return 1
}

OVERLAY=""
OVERLAY="$(resolve_overlay 2>/dev/null || true)"

log "app=${BET}"
if [[ -n "${OVERLAY}" ]]; then
  log "source=local overlay ${OVERLAY}"
else
  log "source=GitHub raw ${GITHUB_REF}"
fi

mkdir -p "${BET}/templates"
BACKUP="${BET}/.cache/template-sync-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir -p "${BACKUP}"

missing_before=()
for tpl in "${TEMPLATES[@]}"; do
  [[ -f "${BET}/templates/${tpl}" ]] || missing_before+=("${tpl}")
done
if [[ ${#missing_before[@]} -gt 0 ]]; then
  log "missing before sync: ${missing_before[*]}"
fi

for tpl in "${TEMPLATES[@]}"; do
  dest="${BET}/templates/${tpl}"
  [[ -f "${dest}" ]] && cp -a "${dest}" "${BACKUP}/${tpl}" 2>/dev/null || true
  if [[ -n "${OVERLAY}" && -f "${OVERLAY}/templates/${tpl}" ]]; then
    install -m 0644 "${OVERLAY}/templates/${tpl}" "${dest}"
    log "installed ${tpl} (local)"
  else
    curl -fsSL "${GITHUB_BASE}/templates/${tpl}" -o "${dest}.tmp"
    mv "${dest}.tmp" "${dest}"
    chmod 0644 "${dest}"
    log "installed ${tpl} (github)"
  fi
done

# Python + filters from same overlay ref when local tree missing
if [[ -n "${OVERLAY}" ]]; then
  rsync -a "${OVERLAY}/src/hibs_predictor/web_format.py" "${BET}/src/hibs_predictor/" 2>/dev/null || true
else
  curl -fsSL "${GITHUB_BASE}/src/hibs_predictor/web_format.py" \
    -o "${BET}/src/hibs_predictor/web_format.py"
fi

LIB="${BET}/scripts/lib_football_dashboard_fix.sh"
if [[ -f "${LIB}" ]]; then
  # shellcheck source=lib_football_dashboard_fix.sh
  source "${LIB}"
  football_vps_ensure_web_format_exports "${BET}" "${OVERLAY}"
  football_vps_patch_web_filters "${BET}"
else
  log "WARN: ${LIB} missing — register fmt_* filters manually"
fi

chown -R www-data:www-data "${BET}/templates" "${BET}/src/hibs_predictor/web_format.py" 2>/dev/null || true

PY="${BET}/.venv/bin/python3"
if [[ -x "${PY}" ]]; then
  log "jinja smoke test"
  sudo -u www-data env HOME="${BET}" DEPLOY_PATH="${BET}" PYTHONPATH="${BET}/src" \
    "${PY}" - "${BET}" <<'PY'
import pathlib
import sys

bet = pathlib.Path(sys.argv[1])
tpl_dir = bet / "templates"
required = [
    "_fixture_row_compact.html",
    "dashboard.html",
    "login.html",
]
for name in required:
    path = tpl_dir / name
    if not path.is_file():
        raise SystemExit(f"missing template: {path}")
text = (tpl_dir / "_fixture_row_compact.html").read_text(encoding="utf-8")
if "_fixture_expand_panel" in text:
    raise SystemExit("_fixture_row_compact.html still includes expand panel")

from hibs_predictor.web import app

with app.app_context():
    for name in required:
        app.jinja_env.get_template(name)
    for fname in ("fmt_prob", "fmt_roi", "fmt_pct", "fmt_num", "fmt_odds"):
        if fname not in app.jinja_env.filters:
            raise SystemExit(f"missing jinja filter: {fname}")
print("templates + filters OK")
PY
fi

# Bust in-process dashboard HTML cache files if present
rm -f "${BET}/.cache"/dashboard_page_* 2>/dev/null || true

log "restart hibs-bet"
systemctl restart hibs-bet
sleep 6

for i in 1 2 3; do
  ping_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 http://127.0.0.1:8000/api/ping 2>/dev/null || echo 000)"
  root_code="$(curl -sS -o /dev/null -w '%{http_code}' --max-time 20 http://127.0.0.1:8000/ 2>/dev/null || echo 000)"
  log "try ${i}: ping=${ping_code} root=${root_code}"
  [[ "${ping_code}" == "200" && "${root_code}" =~ ^(200|302)$ ]] && break
  sleep 3
done

if [[ "${root_code}" == "500" || "${ping_code}" != "200" ]]; then
  log "still failing — last log lines:"
  tail -25 "${BET}/logs/hibs-bet.log" 2>/dev/null || journalctl -u hibs-bet -n 20 --no-pager || true
  exit 1
fi

log "GREEN: overlay templates synced; backup=${BACKUP}"
if grep -q expand_panel "${BET}/templates/_fixture_row_compact.html" 2>/dev/null; then
  log "WARN: expand panel still referenced"
  exit 2
fi
