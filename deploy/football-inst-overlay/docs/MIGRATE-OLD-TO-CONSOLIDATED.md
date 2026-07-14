# Migrate everything: old VPS → consolidated `.52`

## Hosts

| Role | Old | New |
|------|-----|-----|
| Football + racing + trading | `77.68.89.73` | `87.106.100.52` |
| FVE / lines | `77.68.89.75` | `127.0.0.1:8010` on `.52` |

`github-sync` on the new box **does not copy** `.env`, `.cache`, SQLite DBs, or trading secrets. That is why pre-migrate worked and post-migrate feels empty.

---

## Option A — One script on NEW VPS (best)

SSH from **new → old** must work (add your pubkey to `.73` and `.75`):

```bash
# On 87.106.100.52
sudo OLD_MAIN=root@77.68.89.73 OLD_FVE=root@77.68.89.75 \
  bash /opt/hibs-bet/deploy/ops-migrate-from-old-vps.sh
```

Dry run first:

```bash
sudo bash /opt/hibs-bet/deploy/ops-migrate-from-old-vps.sh --dry-run
```

---

## Option B — From your Mac (if new cannot SSH to old)

```bash
NEW=root@87.106.100.52
OLD=root@77.68.89.73
OLDFVE=root@77.68.89.75

# Football — secrets + cache + audit
rsync -avz -e ssh ${OLD}:/opt/hibs-bet/.env ${NEW}:/opt/hibs-bet/
rsync -avz -e ssh ${OLD}:/opt/hibs-bet/.cache/ ${NEW}:/opt/hibs-bet/.cache/
rsync -avz -e ssh ${OLD}:/opt/hibs-bet/data/ ${NEW}:/opt/hibs-bet/data/

# Racing
rsync -avz -e ssh ${OLD}:/opt/hibs-racing/.env ${NEW}:/opt/hibs-racing/ 2>/dev/null || true
rsync -avz -e ssh ${OLD}:/opt/hibs-racing/data/ ${NEW}:/opt/hibs-racing/data/

# Trading shadow history + Alpaca secrets
rsync -avz -e ssh ${OLD}:/opt/trading-core/data/ ${NEW}:/opt/trading-core/data/ 2>/dev/null || true
scp ${OLD}:/etc/trading_secrets ${NEW}:/etc/trading_secrets

# FVE scrape lines
rsync -avz -e ssh ${OLDFVE}:/var/lib/fve/scrape-lines/ ${NEW}:/var/lib/fve/scrape-lines/ 2>/dev/null || \
rsync -avz -e ssh ${OLDFVE}:/mnt/fve-data/scrape-lines/ ${NEW}:/var/lib/fve/scrape-lines/ 2>/dev/null || true

# Fix ownership on new
ssh ${NEW} 'chown -R www-data:www-data /opt/hibs-bet/.env /opt/hibs-bet/.cache /opt/hibs-bet/data /opt/hibs-racing; chmod 640 /opt/hibs-bet/.env; chmod 600 /etc/trading_secrets'
```

Then on **new**:

```bash
sudo bash /opt/hibs-bet/deploy/ensure-vps-stack-wiring.sh --repair
sudo bash /opt/hibs-bet/scripts/install_hands_off_automation.sh
sudo systemctl restart hibs-bet hibs-racing trading-shadow-soak
```

---

## What gets migrated

| Path | Why |
|------|-----|
| `/opt/hibs-bet/.env` | API keys (`FOOTBALL_DATA_ORG_KEY`), auth, engine flags |
| `/opt/hibs-bet/.cache/` | `all_fixtures*.json`, `calibration_v1.json` |
| `/opt/hibs-bet/data/*.sqlite` | Prediction audit, affiliate clicks |
| `/opt/hibs-racing/data/` | `raceform.db`, `feature_store.sqlite` |
| `/opt/trading-core/data/` | Shadow soak logs |
| `/etc/trading_secrets` | Alpaca paper keys |
| FVE `scrape-lines/` | Line shopper data |
| `/mnt/hibs-racing-data/` | If old used block volume |

**Not migrated** (re-create on new): Let's Encrypt certs, nginx vhost (already on `.52`), Docker images (re-pull).

---

## After migrate — verify

```bash
cd /opt/hibs-bet && /opt/hibs-bet/.venv/bin/python3 scripts/diagnose_fixtures_vps.py

# Or full repair (warm + low-source scrape + restart):
sudo bash /opt/hibs-bet/scripts/vps_fixture_repair.sh
```

Legacy one-liner:

```bash
cd /opt/hibs-bet && /opt/hibs-bet/.venv/bin/python3 -c "
from dotenv import load_dotenv; import os, glob
from pathlib import Path
load_dotenv('.env')
v=(os.getenv('FOOTBALL_DATA_ORG_KEY') or '').strip()
cache=os.getenv('HIBS_CACHE_DIR','.cache')
print('key:', 'OK' if len(v)>=8 else 'FAIL')
print('cache:', cache)
print('bundles:', len(glob.glob(f'{cache}/all_fixtures*.json')))
print('audit KB:', Path('data/prediction_audit.sqlite').stat().st_size//1024 if Path('data/prediction_audit.sqlite').is_file() else 0)
"

curl -sS http://127.0.0.1:8000/api/ping | python3 -m json.tool
curl -sS http://127.0.0.1:5003/api/ping 2>/dev/null | head -c 200

# Full repair if football or racing empty:
# sudo bash /opt/hibs-bet/scripts/vps_full_data_repair.sh
```

---

## Keep code fresh without wiping data

```bash
sudo HIBS_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-from-github.sh
# Preserves .env, .cache, data — only updates code
```
