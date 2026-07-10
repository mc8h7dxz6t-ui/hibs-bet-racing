#!/usr/bin/env bash
# Full nine/ten pillar score — engineering + evidence (VPS post-apply).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export PYTHONPATH="${ROOT}/src${PYTHONPATH:+:$PYTHONPATH}"
python3 -c "
from hibs_predictor.nine_ten_score import score_all
import json
print(json.dumps(score_all(), indent=2, default=str))
"
