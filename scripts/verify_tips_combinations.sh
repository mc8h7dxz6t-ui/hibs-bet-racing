#!/usr/bin/env bash
# Probe tip combinations API (Trixie / doubles / Lucky 15) — run on VPS as root.
#
#   bash /opt/hibs-racing/scripts/verify_tips_combinations.sh
#   bash /opt/hibs-racing/scripts/verify_tips_combinations.sh 2026-07-20
set -euo pipefail

DATE="${1:-$(date -u +%F)}"
BET="${HIBS_BET_DEPLOY_PATH:-/opt/hibs-bet}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
SOCK="/opt/hibs-racing/run/racing_execution.sock"
SOCK_LEGACY="/var/run/hibs/racing_execution.sock"

if [[ -f "${BET}/deploy/lib-racing-unix-socket.sh" ]]; then
  # shellcheck source=lib-racing-unix-socket.sh
  source "${BET}/deploy/lib-racing-unix-socket.sh"
fi

probe() {
  local label="$1"
  local url="$2"
  shift 2
  echo "==> ${label}"
  local body code
  body="$(mktemp)"
  code="$(curl -sS -o "${body}" -w '%{http_code}' --max-time 15 "$@" "${url}" 2>/dev/null || echo 000)"
  echo "    HTTP ${code}  bytes=$(wc -c <"${body}" | tr -d ' ')"
  if [[ "${code}" == "200" && -s "${body}" ]]; then
    python3 - "${body}" <<'PY'
import json, sys
path = sys.argv[1]
try:
    d = json.load(open(path, encoding="utf-8"))
except json.JSONDecodeError as e:
    print("    JSON error:", e)
    print("    body head:", open(path, encoding="utf-8", errors="replace").read()[:200])
    sys.exit(0)
combos = d.get("combinations") or []
print("    combinations", len(combos))
for c in combos:
    print("     ", c.get("type"), "|", c.get("label"), "| legs", len(c.get("legs") or []))
print("    tip_count", d.get("tip_count"), "card_date", d.get("card_date"))
PY
  elif [[ -s "${body}" ]]; then
    head -c 200 "${body}" | tr '\n' ' '
    echo ""
  else
    echo "    (empty body — service down or wrong URL)"
  fi
  rm -f "${body}"
  echo ""
}

SOCK_USE=""
if sock="$(racing_unix_socket_visible 2>/dev/null)"; then
  SOCK_USE="${sock}"
elif [[ -S "${SOCK}" ]]; then
  SOCK_USE="${SOCK}"
elif [[ -S "${SOCK_LEGACY}" ]]; then
  SOCK_USE="${SOCK_LEGACY}"
fi

if [[ -n "${SOCK_USE}" ]]; then
  probe "racing unix socket" \
    "http://localhost/api/tips/combinations?date=${DATE}" \
    --unix-socket "${SOCK_USE}"
else
  echo "WARN: racing unix socket missing (${SOCK} and ${SOCK_LEGACY})"
  echo "      sudo bash ${BET}/scripts/vps_racing_hard_recovery.sh"
  echo ""
fi

probe "public HTTPS" \
  "https://${PUBLIC}/api/racing/tips/combinations?date=${DATE}"

probe "public racing prefix" \
  "https://${PUBLIC}/racing/api/tips/combinations?date=${DATE}"

DB="${HIBS_RACING_DB_PATH:-/opt/hibs-racing/data/feature_store.sqlite}"
if [[ -f "${DB}" ]]; then
  echo "==> tipster_tips in SQLite (${DATE})"
  sqlite3 "${DB}" \
    "SELECT COUNT(*) FROM tipster_tips WHERE card_date='${DATE}';" 2>/dev/null \
    | awk '{print "    tips rows:", $0}' || echo "    (tipster_tips table missing — ingest once on /racing/tips)"
fi
