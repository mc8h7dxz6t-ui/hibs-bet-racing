#!/usr/bin/env bash
# Health Telemetry demo — ingest → check → export → verify-bundle.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON="${PYTHON:-python3}"
# shellcheck source=instpp_bootstrap.sh
source "$(dirname "$0")/instpp_bootstrap.sh"
instpp_bootstrap
DB="${1:-./data/demo/health.sqlite}"
TAR="${2:-./data/demo/health_bundle.tar}"
PKTS='[{"ts":"2026-06-01T12:00:00Z","seq":1,"hr":72,"spo2":98},{"ts":"2026-06-01T12:00:01Z","seq":2,"hr":73,"spo2":97}]'
mkdir -p "$(dirname "$DB")" "$(dirname "$TAR")"
# Fresh demo — sequence gate is monotonic per device; stale DB rejects seq=1.
rm -f "$DB" "$TAR" "${DB%.sqlite}_sequence.sqlite" "${DB%.sqlite}_ingress.wal"
echo "── 1/4 Ingest batch ──"
"$PYTHON" -m health_telemetry.cli ingest --device-id ward-7 --packets "$PKTS" --database "$DB"
echo "── 2/4 F1–F9 check ──"
"$PYTHON" -m health_telemetry.cli check --database "$DB"
echo "── 3/4 Export bundle ──"
"$PYTHON" -m health_telemetry.cli export --database "$DB" --tarball "$TAR"
echo "── 4/4 Verify offline ──"
"$PYTHON" -m health_telemetry.cli verify-bundle --tarball "$TAR"
echo "[PASS] Health Telemetry demo → $TAR"
