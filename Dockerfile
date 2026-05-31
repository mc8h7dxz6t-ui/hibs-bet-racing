FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HIBS_RACING_DATA_DIR=/data \
    HIBS_RACING_DB_PATH=/data/feature_store.sqlite \
    HIBS_RACING_SKIP_VENV=1 \
    HOST=0.0.0.0 \
    PORT=5003 \
    TZ=Europe/London

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && curl -fsSLo /usr/local/bin/supercronic \
        https://github.com/aptible/supercronic/releases/download/v0.2.33/supercronic-linux-amd64 \
    && chmod +x /usr/local/bin/supercronic

COPY pyproject.toml README.md ./
COPY src ./src
COPY ingest ./ingest
COPY templates ./templates
COPY static ./static
COPY scripts ./scripts
COPY docker/crontab /etc/crontab
COPY docker/entrypoint.sh /entrypoint.sh

RUN chmod +x /app/scripts/*.sh /entrypoint.sh

COPY data/schema.sql ./data/schema.sql
COPY data/models/lgbm_ranker_features.json ./data/models/lgbm_ranker_features.json

RUN pip install --upgrade pip \
    && pip install -e ".[dev,ranker,web,api]" \
    && pip install "gunicorn>=21.0"

RUN mkdir -p /data /data/models /app/logs

VOLUME ["/data"]

EXPOSE 5003

ENTRYPOINT ["/entrypoint.sh"]
