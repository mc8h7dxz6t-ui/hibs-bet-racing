#!/bin/bash
# Extend May 2026 OOS backtest when raceform.db is updated.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

activate_venv
load_env

RFDB="$(raceform_db)"
echo "=== raceform max date in source ==="
sqlite3 "${RFDB}" "SELECT MAX(date) FROM [table];"

echo "=== ingest from 2026-05-20 ==="
hibs-racing ingest-raceform "${RFDB}" --since 2026-05-20 --sync

echo "=== feature store max date ==="
sqlite3 "${HIBS_RACING_DB_PATH:-./data/feature_store.sqlite}" "SELECT MAX(race_date) FROM runners;"

echo "=== May OOS backtest + CSV export ==="
hibs-racing backtest-replay --start 2026-05-01 --end 2026-05-31 --export-ledger

echo "Done. CSV: exports/Hibs_Racing_OOS_PhaseA_May2026_TrackRecord.csv"
