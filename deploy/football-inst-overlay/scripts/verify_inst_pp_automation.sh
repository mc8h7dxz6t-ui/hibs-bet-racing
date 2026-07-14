#!/usr/bin/env bash
# Verify Inst++ automation markers + log freshness (VPS post-apply).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
export DEPLOY_PATH="${DEPLOY_PATH:-$ROOT}"

python3 -c "
from hibs_predictor.inst_pp_snapshot import automation_health, verify_crons_installed
import json
out = {
    'automation_health': automation_health(app_root='${ROOT}'),
    'cron_markers': verify_crons_installed(),
}
print(json.dumps(out, indent=2, default=str))
ok = out['automation_health'].get('ok') and out['cron_markers'].get('ok')
raise SystemExit(0 if ok else 1)
"
