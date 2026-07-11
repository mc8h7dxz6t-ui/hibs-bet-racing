#!/usr/bin/env bash
# Football dashboard / → 500 fixes (fmt_roi filter, web_format.py, sudoers, overlay discovery).
# shellcheck shell=bash

football_vps_resolve_overlay_root() {
  local bet="${1:-/opt/hibs-bet}"
  local racing="${2:-/opt/hibs-racing}"
  local candidate=""

  if [[ -n "${OVERLAY_ROOT:-}" && -d "${OVERLAY_ROOT}" ]]; then
    echo "${OVERLAY_ROOT}"
    return 0
  fi

  for candidate in \
    "${bet}/deploy/football-inst-overlay" \
    "${racing}/deploy/football-inst-overlay" \
    "$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"; do
    [[ -n "${candidate}" && -d "${candidate}/src/hibs_predictor" ]] || continue
    echo "${candidate}"
    return 0
  done

  return 1
}

football_vps_install_web_format() {
  local bet="${1:-/opt/hibs-bet}"
  local dest="${bet}/src/hibs_predictor/web_format.py"
  local overlay="${2:-}"

  if [[ -f "${dest}" ]]; then
    echo "[dashboard-fix] web_format.py present"
    return 0
  fi

  if [[ -n "${overlay}" && -f "${overlay}/src/hibs_predictor/web_format.py" ]]; then
    install -D -m 0644 "${overlay}/src/hibs_predictor/web_format.py" "${dest}"
    echo "[dashboard-fix] installed web_format.py from overlay"
    return 0
  fi

  cat >"${dest}" <<'PY'
"""Jinja display helpers for football dashboard templates."""

from __future__ import annotations

import math
from typing import Any


def normalize_prob_pct(value: Any) -> float | None:
    if value is None:
        return None
    try:
        num = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(num) or math.isinf(num):
        return None
    if num <= 1.0:
        num *= 100.0
    while num > 100.0:
        num /= 100.0
    return round(max(0.0, min(100.0, num)), 1)


def fmt_num(value: Any, decimals: int = 2, suffix: str = "") -> str:
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(num) or math.isinf(num):
        return "—"
    if decimals == 0:
        return f"{int(round(num))}{suffix}"
    return f"{num:.{decimals}f}{suffix}"


def fmt_pct(value: Any) -> str:
    num = normalize_prob_pct(value)
    if num is None:
        return "—"
    return f"{num:.0f}%"


def fmt_roi(value: Any, decimals: int = 1) -> str:
    """Format edge/ROI percent for value pills (e.g. +12.3%)."""
    if value is None:
        return "—"
    try:
        num = float(value)
    except (TypeError, ValueError):
        return "—"
    if math.isnan(num) or math.isinf(num):
        return "—"
    sign = "+" if num > 0 else ""
    return f"{sign}{num:.{decimals}f}%"
PY
  echo "[dashboard-fix] wrote embedded web_format.py"
}

football_vps_patch_web_filters() {
  local bet="${1:-/opt/hibs-bet}"
  local web_py="${bet}/src/hibs_predictor/web.py"
  local py="${bet}/.venv/bin/python3"
  [[ -f "${web_py}" ]] || { echo "[dashboard-fix] missing ${web_py}" >&2; return 1; }
  [[ -x "${py}" ]] || py=python3

  if grep -q 'add_template_filter(fmt_roi' "${web_py}" 2>/dev/null; then
    echo "[dashboard-fix] web.py already registers fmt_roi"
    return 0
  fi

  HOME="${bet}" PYTHONPATH="${bet}/src" "${py}" - "${web_py}" <<'PY'
import pathlib
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
if 'add_template_filter(fmt_roi' in text or 'add_template_filter("fmt_roi"' in text:
    sys.exit(0)

patch = '''
from hibs_predictor.web_format import fmt_num, fmt_pct, fmt_roi

app.add_template_filter(fmt_num, "fmt_num")
app.add_template_filter(fmt_pct, "fmt_pct")
app.add_template_filter(fmt_roi, "fmt_roi")
'''

needle = 'return str(rank) if rank is not None else str(value or "")'
idx = text.find(needle)
if idx == -1:
    print("ERROR: could not find position_rank filter anchor in web.py", file=sys.stderr)
    sys.exit(1)

end = text.find("\n\n", idx)
if end == -1:
    end = idx + len(needle)
else:
    end += 2

path.write_text(text[:end] + patch + text[end:], encoding="utf-8")
print("patched web.py with fmt_* filters")
PY
}

football_vps_fix_sudoers_requiretty() {
  local bet="${1:-/opt/hibs-bet}"
  local dest="/etc/sudoers.d/hibs-cron"

  if [[ -f "${bet}/deploy/install-hibs-cron-sudoers.sh" ]]; then
    bash "${bet}/deploy/install-hibs-cron-sudoers.sh" && return 0
  fi

  if [[ ! -f "${dest}" ]]; then
    return 0
  fi

  if grep -q '!requiretty' "${dest}" 2>/dev/null; then
    sed -i 's/!requiretty/!use_pty/g' "${dest}"
    visudo -cf "${dest}"
    echo "[dashboard-fix] sudoers: !requiretty → !use_pty"
  fi
}

football_vps_sync_overlay_subset() {
  local bet="${1:-/opt/hibs-bet}"
  local overlay="${2:-}"
  [[ -n "${overlay}" && -d "${overlay}" ]] || return 0

  echo "[dashboard-fix] rsync overlay subset ${overlay}/ -> ${bet}/"
  mkdir -p "${bet}/src/hibs_predictor" "${bet}/templates" "${bet}/scripts"
  rsync -a "${overlay}/src/hibs_predictor/web_format.py" "${bet}/src/hibs_predictor/" 2>/dev/null || true
  rsync -a "${overlay}/src/hibs_predictor/web.py" "${bet}/src/hibs_predictor/" 2>/dev/null || true
  rsync -a "${overlay}/templates/" "${bet}/templates/" 2>/dev/null || true
  rsync -a "${overlay}/scripts/lib_football_dashboard_fix.sh" "${bet}/scripts/" 2>/dev/null || true
  rsync -a "${overlay}/scripts/vps_football_fix_dashboard_500.sh" "${bet}/scripts/" 2>/dev/null || true
  chmod +x "${bet}/scripts/vps_football_fix_dashboard_500.sh" 2>/dev/null || true
}

football_vps_apply_dashboard_fix() {
  local bet="${1:-/opt/hibs-bet}"
  local racing="${2:-/opt/hibs-racing}"
  local overlay=""

  overlay="$(football_vps_resolve_overlay_root "${bet}" "${racing}" 2>/dev/null || true)"
  if [[ -n "${overlay}" ]]; then
    echo "[dashboard-fix] overlay=${overlay}"
    football_vps_sync_overlay_subset "${bet}" "${overlay}"
  else
    echo "[dashboard-fix] no overlay tree — using embedded web_format.py"
  fi

  football_vps_install_web_format "${bet}" "${overlay}"
  football_vps_patch_web_filters "${bet}"
  football_vps_fix_sudoers_requiretty "${bet}"

  chown -R www-data:www-data "${bet}/src/hibs_predictor/web_format.py" "${bet}/src/hibs_predictor/web.py" 2>/dev/null || true
}
