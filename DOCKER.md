# Docker deployment

Fully containerized architecture. Deployable to any standard Linux VPS via a single command:

```bash
cp .env.example .env   # fill RACING_API_*, MATCHBOOK_*, optional webhooks
docker compose up -d --build
```

## What runs inside

| Service | Role |
|---------|------|
| `racing` | Gunicorn Flask app on `:5003`, supercronic @ **06:00 Europe/London** → `scripts/daily_refresh.sh` |
| `nginx` | Reverse proxy on host `:8080` → `racing:5003` |

Persistent state lives in the `hibs_data` volume (`/data/feature_store.sqlite`, `/data/models/`).

## Required before first run

1. Copy `.env.example` → `.env` and set API credentials.
2. Place Kaggle `raceform.db` on the host; default mount: `./raceform.db` → `/raceform/raceform.db` (override with `RACEFORM_DB_PATH` in compose).
3. Copy trained ranker weights to the volume (not in git):

   ```bash
   docker compose run --rm racing cp /app/data/models/lgbm_ranker.txt /data/models/ 2>/dev/null || \
     docker cp data/models/lgbm_ranker.txt hibs-racing:/data/models/lgbm_ranker.txt
   ```

## Verify

```bash
curl -s http://localhost:5003/api/ping
curl -s http://localhost:8080/tracker
docker compose logs -f racing
```

## Daily productized output

After `refresh-cards --paper`, cron runs `hibs-racing notify-daily` (top 3 Smart Portfolio picks). Configure in `.env`:

```bash
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
# and/or
DISCORD_WEBHOOK_URL=...
```

## Bare-metal cron (no Docker)

```bash
./scripts/install_cron.sh   # 06:00 daily_refresh.sh
```

See [DATA_UPGRADE.md](./DATA_UPGRADE.md) for paid API migration.
