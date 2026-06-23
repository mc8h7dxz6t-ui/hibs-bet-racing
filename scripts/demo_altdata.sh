#!/usr/bin/env bash
# Alt-Data demo — poll → check → export → verify-bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
DB="${1:-./data/demo/altdata.sqlite}"
TAR="${2:-./data/demo/altdata_bundle.tar}"
CTX='{"demo_price":42.5,"demo_seats":180,"raw_html":"<td>42.5</td><td>180</td>"}'
mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")"
echo "── 1/4 Poll demo feed ──"
"$PYTHON" -m altdata.cli poll --feed demo_feed --ctx "$CTX" --database "$DB"
echo "── 2/4 F1–F9 check ──"
"$PYTHON" -m altdata.cli check --database "$DB"
echo "── 3/4 Export bundle ──"
"$PYTHON" -m altdata.cli export --database "$DB" --tarball "$TAR"
echo "── 4/4 Verify offline ──"
"$PYTHON" -m altdata.cli verify-bundle --tarball "$TAR"
echo "[PASS] Alt-Data demo → $TAR"
