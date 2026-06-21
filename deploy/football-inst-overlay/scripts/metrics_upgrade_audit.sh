#!/usr/bin/env bash
# Institutional metrics upgrade audit — read-only probes, exit 0 unless --strict.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT}"
STRICT=0
[[ "${1:-}" == "--strict" ]] && STRICT=1

log() { echo "[metrics-audit] $*"; }
warn() { echo "[metrics-audit] WARN: $*" >&2; }
fail() { echo "[metrics-audit] FAIL: $*" >&2; exit 1; }

log "=== Layer 1: institutional config + CLV ==="
if PYTHONPATH=src python3 -m hibs_predictor.main institutional-check > /tmp/hibs_inst_check.json 2>/dev/null; then
  python3 -c "
import json
d=json.load(open('/tmp/hibs_inst_check.json'))
print('institutional_ready:', d.get('institutional_ready'))
print('config_issues:', len(d.get('config_issues') or []))
"
else
  warn "institutional-check failed (missing env?)"
fi

log "=== Layer 2: calibration cache ==="
PYTHONPATH=src python3 - <<'PY' || warn "calibration probe failed"
from hibs_predictor.health_quality_narrative import _audit_ops_summary
ao = _audit_ops_summary()
cal = ao.get("calibration_cache") or {}
print("calibration_cache ok:", cal.get("ok"), "n_leagues:", cal.get("n_leagues"))
clv = ao.get("clv_beat_close_28d") or {}
print("clv_beat_close_28d n:", clv.get("n"), "beat_pct:", clv.get("beat_close_pct"))
PY

log "=== Layer 3: gate profile compare (offline) ==="
if PYTHONPATH=src python3 scripts/compare_gate_profiles.py --days 90 --min-bets 5 > /tmp/gate_compare.json 2>/dev/null; then
  python3 -c "
import json
d=json.load(open('/tmp/gate_compare.json'))
profiles=d.get('profiles') or d
print('gate profiles compared:', len(profiles) if isinstance(profiles, dict) else 'ok')
"
else
  warn "gate compare skipped (no audit DB or insufficient rows)"
fi

log "=== Trading: spread suggestion ==="
SPREAD_AUDIT="${TRADING_SPREAD_AUDIT:-/var/log/trading-core/spread_slippage.jsonl}"
if [[ -f "${SPREAD_AUDIT}" ]]; then
  PYTHONPATH=src python3 scripts/suggest_assumed_spread_bps.py --audit "${SPREAD_AUDIT}" || warn "spread suggest failed"
else
  warn "no spread audit at ${SPREAD_AUDIT} — skip trading spread layer"
fi

log "=== FVE bridge (optional) ==="
if curl -sf "${FVE_API_URL:-http://127.0.0.1:8010}/health" -o /tmp/fve_health.json 2>/dev/null; then
  python3 -c "
import json
d=json.load(open('/tmp/fve_health.json'))
bt=d.get('backtest_slice') or {}
print('FVE backtest_slice n:', bt.get('n'), 'brier:', bt.get('brier_score'))
"
else
  warn "FVE /health unreachable"
fi

log "done"
if [[ "${STRICT}" -eq 1 ]]; then
  python3 -c "
import json
d=json.load(open('/tmp/hibs_inst_check.json'))
if not d.get('institutional_ready'):
    raise SystemExit('institutional_ready false')
" || fail "strict mode: institutional_ready false"
fi
