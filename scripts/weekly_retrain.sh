#!/bin/bash
# Weekly: ingest recent results, rebuild feature matrix, retrain ranker, compare holdout.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

activate_venv
load_env

LOOKBACK_DAYS="${HIBS_WEEKLY_LOOKBACK_DAYS:-14}"
START_DATE="$(lookback_date "${LOOKBACK_DAYS}")"
RFDB="$(raceform_db)"

echo "hibs-racing weekly retrain — results since ${START_DATE}"

run_logged "weekly-ingest-pipeline" \
  hibs-racing ingest-raceform "${RFDB}" --since "${START_DATE}" --pipeline

run_logged "weekly-build-matrix" \
  hibs-racing build-matrix

run_logged "weekly-train-ranker" \
  hibs-racing train-ranker

echo "Weekly retrain completed — check data/models/feature_impact.json for holdout stats."
