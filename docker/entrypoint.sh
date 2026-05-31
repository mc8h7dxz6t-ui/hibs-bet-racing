#!/bin/bash
set -euo pipefail

cd /app

# Raceform mount path override for container layout
if [[ -f /raceform/raceform.db ]]; then
  export RACEFORM_DB_PATH="${RACEFORM_DB_PATH:-/raceform/raceform.db}"
fi

mkdir -p /data /data/models /app/logs

if [[ ! -f /data/models/lgbm_ranker_features.json ]] && [[ -f /app/data/models/lgbm_ranker_features.json ]]; then
  cp /app/data/models/lgbm_ranker_features.json /data/models/
fi

if [[ ! -f "${HIBS_RACING_DB_PATH:-/data/feature_store.sqlite}" ]]; then
  echo "Initializing feature store…"
  hibs-racing init || true
fi

if [[ ! -f /data/models/lgbm_ranker.txt ]]; then
  echo "WARNING: /data/models/lgbm_ranker.txt missing — copy trained model into /data volume or mount at build time."
fi

echo "Starting supercronic (06:00 daily_refresh)…"
supercronic /etc/crontab &
CRON_PID=$!

echo "Starting gunicorn on 0.0.0.0:${PORT:-5003}…"
exec gunicorn \
  --bind "0.0.0.0:${PORT:-5003}" \
  --workers "${GUNICORN_WORKERS:-2}" \
  --timeout 120 \
  --access-logfile - \
  --error-logfile - \
  "hibs_racing.web:create_app()"
