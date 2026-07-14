# Automate everything on consolidated VPS

**One command** after DNS points at `87.106.100.52`:

```bash
# If /opt/hibs-bet exists but scripts are old/missing:
sudo HIBS_SYNC_REF=cursor/full-platform-automation-7e4d \
  bash /opt/hibs-bet/deploy/vps-sync-from-github.sh

sudo bash /opt/hibs-bet/scripts/install_all_platform_automation.sh --skip-sync
```

Or sync + install in one go:

```bash
sudo bash /opt/hibs-bet/scripts/install_all_platform_automation.sh
```

## What gets armed automatically

| Layer | Schedule | What it does |
|-------|----------|--------------|
| **Fixture warm** | every 3h + 06:25 UTC + @reboot | Fills `all_fixtures*.json` outside gunicorn |
| **Daily audit** | 06:35 + 23:05 UTC | pred-log-sync, CLV, snapshots |
| **Seed forward** | 07:35 + 14:35 UTC | Headless evidence snapshots (no login) |
| **Hands-off cycle** | every 30m | Repairs football/FVE/racing/trading data producers |
| **Institutional watchdog** | daily | Grades, cron repair, engineering checks |
| **Racing** | daily + */15 watchdog | Cards, SQLite maintenance |
| **Trading** | shadow recon | Paper soak telemetry |

## If football dashboard is still empty

Automation cannot invent fixtures without a data source. On scrape-first VPS:

```bash
# Option A — Football-Data.org (recommended when API-Sports off)
grep FOOTBALL_DATA_ORG_KEY /opt/hibs-bet/.env

# Option B — re-enable API-Sports when quota returns
# HIBS_DISABLE_API_SPORTS=0 + API_FOOTBALL_KEY in .env

sudo HIBS_FIXTURE_WARM_FORCE_REFRESH=1 \
  bash /opt/hibs-bet/scripts/warm_football_fixtures.sh
tail -30 /var/log/hibs-bet/fixture-warm.log
```

## Verify

```bash
crontab -u www-data -l | grep hibs
tail -20 /var/log/hibs-bet/hands-off-cycle.log
bash /opt/hibs-bet/scripts/verify_inst_pp_automation.sh
curl -sS 'http://127.0.0.1:8000/api/health?light=1' | python3 -m json.tool | head -40
```

## Re-arm after any deploy

```bash
sudo bash /opt/hibs-bet/scripts/install_all_platform_automation.sh --skip-sync
```
