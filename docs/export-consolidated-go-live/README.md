# Consolidated VPS go-live (all four stacks)

One command on the new server (`87.106.100.52`):

```bash
sudo HIBS_VPS_IP=87.106.100.52 HIBS_PUBLIC_HOST=hibs-bet.co.uk \
  bash /opt/hibs-bet/scripts/bootstrap_consolidated_vps_go_live.sh
```

From Mac:

```bash
DEPLOY_HOST=87.106.100.52 ./scripts/bootstrap_consolidated_vps_go_live.sh --remote
```

## Before you run

1. DNS: `hibs-bet.co.uk` → new VPS IP
2. `/opt/hibs-bet/.env` — API keys (or scrape-first profile)
3. `/etc/trading_secrets` — Alpaca paper keys (trading pill; template created if missing)

## What it does

- Installs docker + nginx + venvs
- Writes `/etc/hibs-bet/stack.env` with `FVE_REMOTE_HOST=127.0.0.1`
- Syncs football + racing from GitHub
- Enables `hibs-bet`, `hibs-racing`, `trading-shadow-soak` systemd units
- Starts FVE Docker (redis + api + worker on `:8010`)
- Runs lines collector via hibs `/api/fve/fixtures` (no scrapers PYTHONPATH bug)
- Installs hands-off 30m repair cron
- Runs four-stack green verify

## Verify

```bash
cat /var/log/hibs-bet/three-stack-status.json
curl -sS https://hibs-bet.co.uk/api/ping
curl -sS https://hibs-bet.co.uk/racing/api/ping
curl -sS http://127.0.0.1:9108/live
curl -sS https://hibs-bet.co.uk/fve-api/health
```

## Patch files

If GitHub push blocked, apply patches from this directory on VPS after syncing hibs-bet.
