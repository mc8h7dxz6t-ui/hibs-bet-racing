#!/usr/bin/env bash
# Quick failsafe verify — engineering institutional, evidence may be red.
set -euo pipefail

APP="${DEPLOY_PATH:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "${APP}"
export HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"

"${PY}" scripts/validate_institutional_config.py
"${PY}" -c "
from hibs_predictor.institutional_failsafe import failsafe_report, safe_forward_evidence_gates
import json
print(json.dumps({
    'failsafe': failsafe_report(app_root='${APP}'),
    'forward': {
        'buyer_ready': safe_forward_evidence_gates().get('buyer_ready'),
        'grade': safe_forward_evidence_gates().get('evidence_grade'),
    },
}, indent=2))
"
