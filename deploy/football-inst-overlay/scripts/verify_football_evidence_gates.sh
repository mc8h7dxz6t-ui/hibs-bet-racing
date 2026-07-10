#!/usr/bin/env bash
# Football F1–F9 gate verify (exit 0 when buyer_ready).
set -euo pipefail

APP="${DEPLOY_PATH:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "${APP}"
export HOME="${APP}" PYTHONPATH="${APP}/src" HIBS_PRODUCTION=1
PY="${APP}/.venv/bin/python3"
[[ -x "${PY}" ]] || PY="python3"

exec "${PY}" -c "
import json, sys
from hibs_predictor.forward_evidence import forward_evidence_gates
d = forward_evidence_gates()
if '--json' in sys.argv:
    print(json.dumps(d, indent=2, default=str))
else:
  print('evidence_grade:', d.get('evidence_grade'))
  print('buyer_ready:', d.get('buyer_ready'))
  print('matchdays_7d:', d.get('matchdays_7d'))
sys.exit(0 if d.get('buyer_ready') else 1)
" "$@"
