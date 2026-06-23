#!/usr/bin/env bash
# Alt-Data demo — stub poll + optional production URL feed.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
DB="${1:-./data/demo/altdata.sqlite}"
TAR="${2:-./data/demo/altdata_bundle.tar}"
CTX='{"demo_price":42.5,"demo_seats":180,"raw_html":"<td>42.5</td><td>180</td>"}'
SKIP_LIVE="${SKIP_LIVE:-0}"
mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")"
echo "── 1/5 Poll stub feed (offline) ──"
"$PYTHON" -m altdata.cli poll --feed demo_feed --ctx "$CTX" --database "$DB"
if [ "$SKIP_LIVE" != "1" ]; then
  echo "── 2/5 Poll production feed (Frankfurter FX API) ──"
  "$PYTHON" -m altdata.cli poll \
    --feed fx_live \
    --production-feed fx_gbp_cross \
    --database "$DB" || echo "[WARN] production fetch skipped (network)"
else
  echo "── 2/5 Production feed skipped (SKIP_LIVE=1) ──"
fi
echo "── 3/5 F1–F9 check ──"
"$PYTHON" -m altdata.cli check --database "$DB"
echo "── 4/5 Export bundle ──"
"$PYTHON" -m altdata.cli export --database "$DB" --tarball "$TAR"
echo "── 5/5 Verify offline ──"
"$PYTHON" -m altdata.cli verify-bundle --tarball "$TAR"
echo "[PASS] Alt-Data demo → $TAR"
