#!/usr/bin/env bash
# Post-deploy observation — curl all product health endpoints and print headline scores.
#
#   sudo bash /opt/hibs-bet/deploy/ops-observe-stack.sh
#   HIBS_PUBLIC_HOST=hibs-bet.co.uk sudo bash /opt/hibs-bet/deploy/ops-observe-stack.sh
set -euo pipefail

APP="${DEPLOY_PATH:-/opt/hibs-bet}"
RACING="${HIBS_RACING_DEPLOY_PATH:-/opt/hibs-racing}"
PUBLIC="${HIBS_PUBLIC_HOST:-hibs-bet.co.uk}"
FVE_URL="${FVE_API_URL:-http://127.0.0.1:8010}"
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY=python3

section() { echo ""; echo "======== $* ========"; }

section "Deploy revisions"
for f in "${APP}/.deploy-revision" "${RACING}/.deploy-revision" /opt/fve/.deploy-revision; do
  [[ -f "${f}" ]] && { echo "--- ${f}"; cat "${f}"; } || echo "missing ${f}"
done

section "Systemd units"
for u in hibs-bet hibs-racing trading-shadow-soak nginx; do
  printf "  %-22s %s\n" "${u}" "$(systemctl is-active "${u}" 2>/dev/null || echo n/a)"
done

section "Football /api/health (local)"
curl -fsS --max-time 15 "http://127.0.0.1:8000/api/health?full=1" 2>/dev/null | \
  "${PY}" -c "
import json,sys
d=json.load(sys.stdin)
ao=d.get('audit_ops') or {}
clv=ao.get('clv_beat_close_28d') or {}
print('institutional_ready:', d.get('institutional_ready'))
print('clv_beat_close_28d n:', clv.get('n'), 'beat_pct:', clv.get('beat_close_pct'))
so=d.get('stack_ops') or {}
print('racing_evidence:', (so.get('racing_evidence') or {}).get('buyer_ready'))
print('trading_ops:', (so.get('trading') or {}).get('score'))
" 2>/dev/null || echo "WARN: football health failed"

section "Racing /api/health"
curl -fsS --max-time 12 "http://127.0.0.1:5003/api/health?full=1" 2>/dev/null | \
  "${PY}" -c "
import json,sys
d=json.load(sys.stdin)
p=d.get('paper') or {}
rel=d.get('reliability') or {}
print('runners:', d.get('runners_loaded'), 'recon_clean:', d.get('recon_clean'))
print('paper n_rows:', p.get('n_rows'), 'settled:', p.get('settled'))
print('reliability n:', rel.get('n'), 'brier:', rel.get('brier_score'))
" 2>/dev/null || echo "WARN: racing health failed"

section "FVE /health"
curl -fsS --max-time 10 "${FVE_URL}/health" 2>/dev/null | \
  "${PY}" -c "
import json,sys
d=json.load(sys.stdin)
bt=d.get('backtest_slice') or {}
print('status:', d.get('status'), 'paused:', d.get('paused'))
print('feed_mode:', d.get('feed_mode'), 'worker:', (d.get('worker') or {}).get('alive'))
print('backtest n:', bt.get('n'), 'brier:', bt.get('brier_score'))
" 2>/dev/null || echo "WARN: FVE health failed (${FVE_URL})"

section "FVE via hibs proxy"
curl -fsS --max-time 12 "http://127.0.0.1:8000/api/fve/status?full=1" 2>/dev/null | \
  "${PY}" -c "
import json,sys
d=json.load(sys.stdin)
print('reachable:', d.get('reachable'), 'paused:', d.get('paused'), 'worker_live:', d.get('worker_live'))
bt=d.get('backtest_slice') or {}
print('backtest_slice n:', bt.get('n'))
" 2>/dev/null || echo "WARN: /api/fve/status failed"

section "Trading /ready"
curl -fsS --max-time 8 "http://127.0.0.1:9108/ready" 2>/dev/null || echo "WARN: trading-shadow not ready"

section "Public URLs (if nginx up)"
for path in / /racing/ /line-trader /harvested-execution; do
  code=$(curl -sS -o /dev/null -w '%{http_code}' --max-time 12 "https://${PUBLIC}${path}" 2>/dev/null || echo 000)
  printf "  https://%-30s %s\n" "${PUBLIC}${path}" "${code}"
done

section "Disk / volumes"
df -h / /opt/hibs-bet /opt/hibs-racing /mnt/hibs-racing-data /mnt/fve-data 2>/dev/null | grep -v tmpfs || df -h /

echo ""
echo "Watch live:"
echo "  journalctl -u hibs-bet -f"
echo "  journalctl -u hibs-racing -f"
echo "  open https://${PUBLIC}/line-trader"
echo "  open https://${PUBLIC}/racing/"
echo "  open https://${PUBLIC}/harvested-execution"
