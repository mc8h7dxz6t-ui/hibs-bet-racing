#!/usr/bin/env bash
# Post-deploy audits for McFadden win engine + tip combinations stack.
#
#   ./scripts/verify_win_engine_deploy.sh
#   HIBS_PRODUCTION_URL=https://hibs-bet.co.uk ./scripts/verify_win_engine_deploy.sh
#   HIBS_RACING_DB_PATH=/opt/hibs-racing/data/feature_store.sqlite ./scripts/verify_win_engine_deploy.sh
set -euo pipefail

FOOTBALL="${HIBS_PRODUCTION_URL:-https://hibs-bet.co.uk}"
COMBOS_DATE="${HIBS_VERIFY_COMBOS_DATE:-2026-05-31}"
DB_PATH="${HIBS_RACING_DB_PATH:-}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ -z "${DB_PATH}" ]]; then
  for candidate in \
    "${REPO_ROOT}/data/feature_store.sqlite" \
    "/opt/hibs-racing/data/feature_store.sqlite" \
    "/opt/hibs-bet-racing/data/feature_store.sqlite"; do
    if [[ -f "${candidate}" ]]; then
      DB_PATH="${candidate}"
      break
    fi
  done
fi

fail=0
pass() { echo "  OK   $*"; }
warn() { echo "  WARN $*"; }
bad() { echo "  FAIL $*"; fail=1; }

TMP="${TMPDIR:-/tmp}/hibs-win-engine-verify-$$"
mkdir -p "${TMP}"
trap 'rm -rf "${TMP}"' EXIT

echo "==> Win engine + combinations deploy audit"
echo "    Football URL: ${FOOTBALL}"
echo "    DB path:      ${DB_PATH:-<not found — HTTP checks only>}"
echo

echo "==> 1) Combinations parsing API"
comb_url="${FOOTBALL}/api/racing/tips/combinations?date=${COMBOS_DATE}"
comb_code="$(curl -sS -o "${TMP}/combos.json" -w '%{http_code}' --max-time 30 "${comb_url}" || echo 000)"
if [[ "${comb_code}" == "200" ]]; then
  if python3 -c "
import json, sys
d = json.load(open('${TMP}/combos.json'))
assert d.get('ok') is True
assert 'combinations' in d and 'singles' in d
sys.exit(0)
" 2>/dev/null; then
    pass "${comb_url} -> 200 with combinations + singles"
    if python3 -c "
import json
d=json.load(open('${TMP}/combos.json'))
sys.exit(0 if 'win_engine' not in d else 1)
" 2>/dev/null; then
      pass "win_engine block absent (expected when inactive)"
    else
      warn "win_engine block present — HIBS_WIN_ENGINE_ACTIVE may be true + calibrated"
    fi
  else
    bad "${comb_url} -> 200 but invalid JSON shape"
  fi
else
  bad "${comb_url} -> ${comb_code}"
fi

echo
echo "==> 2) Win engine API cloak (inactive sandbox)"
we_url="${FOOTBALL}/api/racing/win-engine/predictions"
we_headers="$(curl -i -s --max-time 20 "${we_url}" -o "${TMP}/we.json" | head -1 || true)"
we_code="$(curl -sS -o "${TMP}/we.json" -w '%{http_code}' --max-time 20 "${we_url}" || echo 000)"
if [[ "${we_code}" == "404" ]]; then
  pass "${we_url} -> 404 (cloaked from public release)"
  if grep -qi 'win_engine_inactive' "${TMP}/we.json" 2>/dev/null; then
    pass "response cites win_engine_inactive"
  fi
elif [[ "${we_code}" == "200" ]]; then
  warn "${we_url} -> 200 — engine is ACTIVE and calibrated on this host"
else
  bad "${we_url} -> ${we_code} (expected 404 when inactive)"
fi

echo
echo "==> 3) SQLite schema (win_engine_predictions)"
if [[ -n "${DB_PATH}" && -f "${DB_PATH}" ]]; then
  cols="$(sqlite3 "${DB_PATH}" "PRAGMA table_info(win_engine_predictions);" 2>/dev/null || true)"
  if [[ -z "${cols}" ]]; then
    bad "win_engine_predictions table missing — run init_db / deploy migration"
  else
    for col in runner_id race_id true_probability fair_odds brier_score timestamp matchbook_back_odds race_field_brier field_size; do
      if echo "${cols}" | grep -q "|${col}|"; then
        pass "column ${col} present"
      else
        bad "column ${col} missing"
      fi
    done
    cal="$(sqlite3 "${DB_PATH}" "SELECT calibration_state, rolling_brier, sample_n, variable_bounds_pass, market_beat_pass, exchange_beat_delta_bps FROM win_engine_calibration WHERE id=1;" 2>/dev/null || true)"
    if [[ -n "${cal}" ]]; then
      pass "win_engine_calibration row: ${cal}"
    else
      warn "win_engine_calibration empty — first refresh-cards will seed"
    fi
  fi
else
  warn "Skipping DB checks — set HIBS_RACING_DB_PATH or run on VPS"
fi

echo
echo "==> 4) Football dashboard UI mount"
dash_code="$(curl -sS -o "${TMP}/dash.html" -w '%{http_code}' --max-time 45 "${FOOTBALL}/" || echo 000)"
if [[ "${dash_code}" == "200" ]]; then
  if grep -q 'id="system-bets-mount"' "${TMP}/dash.html"; then
    pass "system-bets-mount present in dashboard HTML"
  else
    bad "system-bets-mount missing — hibs-bet UI PR not deployed?"
  fi
  if grep -q 'hibs_system_bets.js' "${TMP}/dash.html"; then
    pass "hibs_system_bets.js referenced"
  else
    warn "hibs_system_bets.js not found in HTML"
  fi
  if grep -q 'system-bets-fold' "${TMP}/dash.html"; then
    pass "system-bets-fold sidebar wrapper present"
  fi
else
  bad "dashboard ${FOOTBALL}/ -> ${dash_code}"
fi

echo
if [[ "${fail}" -eq 0 ]]; then
  echo "Win engine deploy audit: GREEN"
  exit 0
fi
echo "Win engine deploy audit: issues found — see docs/WIN_ENGINE_DEPLOYMENT.md"
exit 1
