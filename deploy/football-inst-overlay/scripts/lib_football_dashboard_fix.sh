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


def fmt_prob(value: Any, decimals: int = 1) -> str:
    num = normalize_prob_pct(value)
    if num is None:
        return "—"
    if decimals <= 0:
        return f"{num:.0f}%"
    return f"{num:.{decimals}f}%"


def fmt_odds(value: Any, decimals: int = 2) -> str:
    return fmt_num(value, decimals)


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

football_vps_ensure_web_format_exports() {
  local bet="${1:-/opt/hibs-bet}"
  local dest="${bet}/src/hibs_predictor/web_format.py"
  [[ -f "${dest}" ]] || return 0
  if grep -q 'def fmt_prob' "${dest}" 2>/dev/null && grep -q 'def fmt_odds' "${dest}" 2>/dev/null; then
    return 0
  fi
  football_vps_install_web_format "${bet}" ""
  echo "[dashboard-fix] refreshed web_format.py (fmt_prob/fmt_odds)"
}

football_vps_patch_web_filters() {
  local bet="${1:-/opt/hibs-bet}"
  local web_py="${bet}/src/hibs_predictor/web.py"
  local py="${bet}/.venv/bin/python3"
  [[ -f "${web_py}" ]] || { echo "[dashboard-fix] missing ${web_py}" >&2; return 1; }
  [[ -x "${py}" ]] || py=python3

  HOME="${bet}" PYTHONPATH="${bet}/src" "${py}" - "${web_py}" <<'PY'
import pathlib
import re
import sys

path = pathlib.Path(sys.argv[1])
text = path.read_text(encoding="utf-8")

filters = ("fmt_num", "fmt_pct", "fmt_prob", "fmt_odds", "fmt_roi")
missing = [name for name in filters if f'add_template_filter({name}' not in text and f'add_template_filter("{name}"' not in text]
if not missing:
    print("web.py already registers all fmt_* filters")
    sys.exit(0)

import_line = "from hibs_predictor.web_format import fmt_num, fmt_odds, fmt_pct, fmt_prob, fmt_roi"
if "from hibs_predictor.web_format import" in text:
    text = re.sub(
        r"from hibs_predictor\.web_format import[^\n]+",
        import_line,
        text,
        count=1,
    )
else:
    needle = 'return str(rank) if rank is not None else str(value or "")'
    idx = text.find(needle)
    if idx == -1:
        print("ERROR: could not find position_rank filter anchor in web.py", file=sys.stderr)
        sys.exit(1)
    end = text.find("\n\n", idx)
    end = end + 2 if end != -1 else idx + len(needle)
    block = "\n" + import_line + "\n\n"
    for name in filters:
        block += f'app.add_template_filter({name}, "{name}")\n'
    block += "\n"
    text = text[:end] + block + text[end:]

for name in missing:
    if f'add_template_filter({name}' in text or f'add_template_filter("{name}"' in text:
        continue
    insert_at = text.rfind("app.add_template_filter(")
    if insert_at == -1:
        print(f"ERROR: cannot place filter registration for {name}", file=sys.stderr)
        sys.exit(1)
    line_end = text.find("\n", insert_at)
    text = text[: line_end + 1] + f'app.add_template_filter({name}, "{name}")\n' + text[line_end + 1 :]

path.write_text(text, encoding="utf-8")
print("patched web.py filters:", ", ".join(missing))
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

football_vps_install_safe_fixture_row() {
  local bet="${1:-/opt/hibs-bet}"
  local overlay="${2:-}"
  local dest="${bet}/templates/_fixture_row_compact.html"
  local expand="${bet}/templates/_fixture_expand_panel.html"

  if [[ -f "${dest}" ]] && ! grep -q '_fixture_expand_panel' "${dest}" 2>/dev/null; then
    echo "[dashboard-fix] fixture row already compact (no expand panel)"
    return 0
  fi

  if [[ -n "${overlay}" && -f "${overlay}/templates/_fixture_row_compact.html" ]]; then
    cp -a "${dest}" "${dest}.bak.$(date +%s)" 2>/dev/null || true
    install -m 0644 "${overlay}/templates/_fixture_row_compact.html" "${dest}"
    echo "[dashboard-fix] installed overlay _fixture_row_compact.html"
    return 0
  fi

  cp -a "${dest}" "${dest}.bak.$(date +%s)" 2>/dev/null || true
  cat >"${dest}" <<'HTML'
{# Compact fixture row for dashboard — overlay must include (was missing on VPS → 500). #}
{% set fx = fixture %}
{% set pred = fx.prediction if fx.prediction is mapping else {} %}
{% set odds = fx.best_odds_1x2 if fx.best_odds_1x2 is mapping else {} %}
{% set dq = fx.data_quality.score_pct if fx.data_quality is mapping and fx.data_quality.score_pct is not none else (fx.data_quality_pct or 0) %}
{% set fid = fx.id or fx.fixture_id or loop.index %}
{% set home = fx.home_team or fx.home or 'Home' %}
{% set away = fx.away_team or fx.away or 'Away' %}
{% set ko = fx.kickoff_display or fx.kickoff_local or fx.date or '—' %}
{% set ph = pred.home_win_prob or pred.prob_home or pred.get('1') %}
{% set pd = pred.draw_prob or pred.prob_draw or pred.get('X') %}
{% set pa = pred.away_win_prob or pred.prob_away or pred.get('2') %}
{% set btts = pred.btts_yes_prob or pred.btts_prob %}
{% set win_lean = pred.predicted_outcome or pred.lean_1x2 or '—' %}
<details class="fr-compact fixture-card{% if fx.has_value_bet %} value-card{% endif %}"
    data-fid="{{ fid }}"
    data-league="{{ fx.league or '' }}"
    data-region="{{ fx.dashboard_region or 'other' }}"
    data-has-value="{{ '1' if fx.has_value_bet else '0' }}"
    data-data-q="{{ dq }}"
    data-search="{{ (home ~ ' ' ~ away ~ ' ' ~ (fx.league_name or fx.league or ''))|lower }}"
    data-kickoff-utc="{{ fx.kickoff_iso or fx.kickoff_utc or '' }}"
    data-is-live="{{ '1' if fx.is_live else '0' }}"
    id="fix-{{ fid }}">
    <summary class="fr-sum fixture-summary">
        <div class="fr-sum-grid">
            <span class="fr-ko">{{ ko }}</span>
            <span class="fr-match">{{ home }} <span class="fr-vs">v</span> {{ away }}</span>
            <span class="fr-prob">{% if btts is not none %}{{ '%.0f'|format(btts * 100 if btts <= 1 else btts) }}%{% else %}<span class="fr-prob-na">—</span>{% endif %}</span>
            <span class="fr-prob fr-prob-win"><span class="fr-win-lean">{{ win_lean }}</span></span>
            <span class="fr-od">{% if odds.home %}{{ '%.2f'|format(odds.home) }}{% else %}—{% endif %}</span>
            <span class="fr-od">{% if odds.draw %}{{ '%.2f'|format(odds.draw) }}{% else %}—{% endif %}</span>
            <span class="fr-od">{% if odds.away %}{{ '%.2f'|format(odds.away) }}{% else %}—{% endif %}</span>
            <span class="fr-od fr-prob-na">—</span>
            <span class="fr-od fr-prob-na">—</span>
            <span class="fr-od fr-prob-na">—</span>
            <span class="fr-od fr-prob-na">—</span>
            <span class="fr-od fr-prob-na">—</span>
            <span class="fr-od fr-prob-na">—</span>
            <span class="fr-dq-compact" title="Data quality">{{ '%.0f'|format(dq) }}%</span>
        </div>
    </summary>
    <div class="expand-panel fr-sum-meta">
        {% if fx.has_value_bet %}<span class="fr-value-box">Value</span>{% endif %}
        <span class="fr-league">{{ fx.league_name or fx.league or '' }}</span>
    </div>
</details>
HTML
  echo "[dashboard-fix] installed embedded safe _fixture_row_compact.html"
  if [[ -f "${expand}" ]]; then
    echo "[dashboard-fix] note: _fixture_expand_panel.html left in place but no longer included"
  fi
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
  football_vps_ensure_web_format_exports "${bet}"
  football_vps_patch_web_filters "${bet}"
  football_vps_install_safe_fixture_row "${bet}" "${overlay}"
  football_vps_fix_sudoers_requiretty "${bet}"

  chown -R www-data:www-data "${bet}/src/hibs_predictor/web_format.py" "${bet}/src/hibs_predictor/web.py" "${bet}/templates/_fixture_row_compact.html" 2>/dev/null || true
}
