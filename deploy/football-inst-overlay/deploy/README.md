# Deploy

**GitLab CI (hibs-bet.co.uk):** see [GITLAB_DEPLOY.md](GITLAB_DEPLOY.md) — variables, SSH key, push-to-`main` pipeline.

## Production (`hibs-bet.service`)

- Gunicorn binds **0.0.0.0:8000** (see `hibs-bet.service`).
- Working directory: `/opt/hibs-bet` (adjust on your server).
- Secrets: `/opt/hibs-bet/.env` (from `.env.example`).

```bash
sudo cp deploy/hibs-bet.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hibs-bet
```

### Link local hibs-bet to hibs-bet.co.uk

Production today: **DNS** `hibs-bet.co.uk` → `77.68.89.73`, **app** at `/opt/hibs-bet`, **nginx** → gunicorn `:8000`.

```bash
# Check DNS, HTTPS, and whether production matches your local git commit
./scripts/verify_domain_link.sh

# Deploy this folder to the VPS and re-check (needs SSH key for root@77.68.89.73)
./scripts/link_production.sh
```

After deploy, `https://hibs-bet.co.uk/api/ping` includes `revision` (git SHA) so you can confirm the live site matches your Mac checkout.

**GitHub Actions:** add repo secrets `DEPLOY_HOST`, `DEPLOY_USER`, `SSH_PRIVATE_KEY` — pushes to `main` run `.github/workflows/deploy.yml`.

### Link hibs-racing to hibs-bet.co.uk/racing

Racing runs as a **twin app** on the same VPS and hostname (no separate domain required):

| Piece | Path / port |
|-------|-------------|
| Public URL | `https://hibs-bet.co.uk/racing` (cards at `/racing/cards`) |
| gunicorn | `127.0.0.1:5003` (`hibs-racing.service`) |
| VPS code | `/opt/hibs-racing` |
| Portfolio API (football bar) | `/api/racing/portfolio/summary` → racing `:5003` |

From your Mac (local repo `~/hibs-racing`, engine already working):

```bash
# Check whether /racing is live and matches your local racing commit
./scripts/verify_racing_link.sh

# Deploy ~/hibs-racing + nginx proxy + football cross-links
./scripts/link_racing_production.sh

# Football + racing together
./scripts/verify_hibs_stack_link.sh
```

Override local racing path if needed: `HIBS_RACING_REPO=~/path/to/hibs-racing ./scripts/deploy_racing_to_vps.sh`

**Racing `/racing` subpath** (product switcher, nav, portfolio API): post-deploy runs
`deploy/patch_racing_web_production.py` automatically. If you see localhost links or 404s on
`/api/portfolio/summary` when switching to Racing, one-shot on VPS:

```bash
curl -fsSL https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet/main/scripts/patch_racing_production_urls.sh | ssh root@77.68.89.73 'bash -s'
```

Or from Mac: `./scripts/patch_racing_production_urls.sh` (after `refresh_deploy_scripts.sh`).

### HTTPS (nginx + Let's Encrypt)

Gunicorn only listens on **:8000**. For `https://hibs-bet.co.uk`:

```bash
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo cp deploy/hibs-bet.nginx.conf /etc/nginx/sites-available/hibs-bet
sudo ln -sf /etc/nginx/sites-available/hibs-bet /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d hibs-bet.co.uk -d www.hibs-bet.co.uk
```


### Safer full data (~2GB VPS)

Balanced profile: 7-day fixture window, `HIBS_MAX_DATA=1`, live dashboard (`HIBS_DASHBOARD_LITE=0`), skip heavy scrapes when APIs are strong, 3 fixture workers, warm cache, player/injury insight flags. Gunicorn **2 workers**, **180s** timeout.

```bash
sudo bash /opt/hibs-bet/deploy/apply-vps-safe-production.sh
```

**From your Mac:** SSH must use your deploy key (`root@77.68.89.73`). If you see `Permission denied (publickey,password)`, the Cursor agent sandbox cannot use your Mac keychain — run the script locally:

```bash
ssh root@77.68.89.73 'cd /opt/hibs-bet && git pull && sudo bash deploy/apply-vps-safe-production.sh'
```

Or pipe the script: `ssh root@77.68.89.73 'bash -s' < deploy/apply-vps-safe-production.sh` (after `git pull` on the server so the script exists).

### 1 GB VPS tuning (worker timeout / OOM)

Default unit uses **1 worker** and **300s** timeout. After deploy, on the server:

```bash
sudo bash /opt/hibs-bet/deploy/apply-vps-production-tuning.sh
```

Sets `www-data` ownership on `.cache`, appends lite `.env` flags (`HIBS_DASHBOARD_LITE`, `HIBS_WARM_FIXTURE_CACHE`, …), patches nginx timeouts, restarts `hibs-bet`.

## Staging (`hibs-bet-staging.service`)

Run staging **beside** production on a different port and cache directory so you can test `HIBS_MAX_DATA=1`, Scottish FBref xG, and UI changes without touching live traffic.

| | Production | Staging |
|---|------------|---------|
| Unit | `hibs-bet.service` | `hibs-bet-staging.service` |
| Port | 8000 | **8001** |
| Env file | `.env` | **`.env.staging`** |
| Cache | `.cache` (default) | **`.cache-staging`** |

```bash
# On server (example paths)
sudo mkdir -p /opt/hibs-bet-staging
# deploy code + venv, then:
cp deploy/staging.env.example /opt/hibs-bet-staging/.env.staging
# edit keys in .env.staging

sudo cp deploy/hibs-bet-staging.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now hibs-bet-staging
```

Local dev (no systemd): `PORT=5002 PYTHONPATH=src python3 src/hibs_predictor/web.py` with `HIBS_CACHE_DIR=.cache-staging` in `.env`.

## Trading core — shadow forward soak (`trading-shadow-soak.service`)

Long-running **shadow** deployment for OOS evidence: Alpaca market stream, `SHADOW_WOULD_ROUTE` strategy audits, spread JSONL, **zero** live WAL submits. See [TRADING_A_PLUS_EXECUTION_PLAN.md](../docs/TRADING_A_PLUS_EXECUTION_PLAN.md) and [TRADING_PROMOTION_SCORECARD.md](../docs/TRADING_PROMOTION_SCORECARD.md).

| Artifact | Role |
|----------|------|
| `deploy/install-harvested-execution-shadow.sh` | **Recommended:** user, secrets check, Phase 3, systemd units + timer |
| `deploy/trading-shadow-soak.service` | systemd unit (Phase 3 preflight + 30-day soak) |
| `deploy/trading-evidence-snapshot.{service,timer}` | Daily manifest + invariant verify (00:15 UTC) |
| `deploy/trading_secrets.template` | Copy to `/etc/trading_secrets` (mode `600`, root-owned) |

```bash
# On server — after repo at /opt/trading-core and Alpaca paper keys in /etc/trading_secrets
sudo bash /opt/trading-core/deploy/install-harvested-execution-shadow.sh --install-root /opt/trading-core
```

**Manual install** (equivalent):

```bash
# On server (example install root /opt/trading-core)
sudo useradd -r -s /usr/sbin/nologin trading_executor
sudo groupadd -f trading_ops
sudo usermod -aG trading_ops trading_executor
sudo mkdir -p /opt/trading-core/data
sudo chown -R trading_executor:trading_ops /opt/trading-core/data

sudo cp deploy/trading_secrets.template /etc/trading_secrets
sudo chmod 600 /etc/trading_secrets && sudo chown root:root /etc/trading_secrets
# edit keys: ALPACA_*, TRADING_HMAC_SECRET, METRICS_PORT=9108, TRADING_*_DB paths

sudo cp deploy/trading-shadow-soak.service /etc/systemd/system/
sudo cp deploy/trading-evidence-snapshot.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now trading-shadow-soak
sudo systemctl enable --now trading-evidence-snapshot.timer
```

**Verify**

```bash
sudo journalctl -u trading-shadow-soak -f -n 50
curl -s http://127.0.0.1:9108/metrics | grep trading_node_ready
```

**Harvested Execution notes**

- `ExecStartPre` runs the **full** Phase 3 gate before each start (after failures). A failed gate blocks soak — intentional.
- Set `METRICS_PORT` in `/etc/trading_secrets` so Prometheus can scrape a stable port (ephemeral `0` is for local dev only).
- Successful 30-day completion exits cleanly; `Restart=on-failure` does **not** auto-relaunch a finished soak.
- Adjust `WorkingDirectory`, venv paths, and `ReadWritePaths` in the unit if your install root is not `/opt/trading-core`.

## Trading core — Alpaca paper phase (`trading-paper.service`)

Broker **submits allowed** on Alpaca paper (caps: $1k/order, $10k gross). Uses **port 9109** so shadow soak can keep **9108**. See [TRADING_PAPER_START.md](../docs/TRADING_PAPER_START.md).

| Artifact | Role |
|----------|------|
| `deploy/install-harvested-execution-paper.sh` | Install + enable `trading-paper` |
| `deploy/trading-paper.service` | systemd unit (Phase 3 preflight + orchestrator) |
| `deploy/paper.env.example` | Starter `.env` block for Mac dev |
| `scripts/start_paper_trading.sh` | Local dev without systemd |
| `scripts/link_paper_trading.sh` | Mac → VPS deploy + start paper alongside shadow |

```bash
# Mac — paper on VPS (shadow soak can stay on :9108)
./scripts/link_paper_trading.sh

# Mac dev only
./scripts/start_paper_trading.sh

# Server manual
sudo bash /opt/trading-core/deploy/install-harvested-execution-paper.sh --install-root /opt/trading-core
sudo journalctl -u trading-paper -f
curl -s http://127.0.0.1:9109/metrics | grep trading_node_ready
```

### Daily evidence snapshots

```bash
sudo cp deploy/trading-evidence-snapshot.{service,timer} /etc/systemd/system/
sudo systemctl enable --now trading-evidence-snapshot.timer
```

Runs `collect_trading_evidence.py --daily` and `verify_shadow_invariants.py`. See [docs/TRADING_EVIDENCE_RUNBOOK.md](../docs/TRADING_EVIDENCE_RUNBOOK.md).

**Promotion (day 31):**

```bash
cd /opt/trading-core
PYTHONPATH=src python3 scripts/evaluate_promotion_scorecard.py \
  --transition shadow_to_micro \
  --evidence-daily-dir data/evidence/daily \
  --phase3-gate-passed \
  --output-md data/evidence/promotion_scorecard.md
```

Exit **0 = GO** for shadow → micro. See [TRADING_PROMOTION_SCORECARD.md](../docs/TRADING_PROMOTION_SCORECARD.md).

## FVE on a dedicated 1GB VPS (split stack)

| Host | IP | Role |
|------|-----|------|
| `hibs-bet-vps` | `77.68.89.73` | Football, racing, trading, nginx, **line-trader UI** |
| `vps` (1GB) | `77.68.89.75` | FVE only: Redis + API + ingest worker on `:8010` |

**1.** On the **1GB FVE box**:

```bash
sudo HIBS_UPSTREAM_BASE_URL=https://hibs-bet.co.uk HIBS_MAIN_IP=77.68.89.73 \
  bash /opt/hibs-bet/deploy/bootstrap-fve-dedicated-1gb.sh
```

Adds 1GB swap, docker memory caps, firewall `:8010` from main IP only.

**Block storage (recommended on 10GB root):** attach 20GB in the panel, `lsblk`, then:

```bash
sudo VOLUME_DEVICE=/dev/sdb HIBS_UPSTREAM_BASE_URL=https://hibs-bet.co.uk HIBS_MAIN_IP=77.68.89.73 \
  bash bootstrap-fve-dedicated-1gb.sh
```

Mounts Docker data + scrape lines on the volume.

## Racing SQLite on block storage (main VPS)

Attach **20GB** to `hibs-bet-vps`, then:

```bash
lsblk
sudo VOLUME_DEVICE=/dev/sdb bash /opt/hibs-bet/deploy/mount-racing-data-volume.sh
```

Moves `feature_store.sqlite`, `raceform.db`, parquet to `/mnt/hibs-racing-data`, enables `HIBS_RACING_SQLITE_BEEFY=1` (64MB cache + mmap). Weekly WAL checkpoint cron already installed.

**2.** On **hibs-bet-vps** (after merge/sync):

```bash
sudo FVE_REMOTE_HOST=77.68.89.75 bash /opt/hibs-bet/deploy/apply-vps-fve-remote-host.sh
```

Sets `FVE_API_URL=http://77.68.89.75:8010`, nginx `/fve-api/` → remote, restarts hibs-bet.

**Verify:** `https://hibs-bet.co.uk/line-trader` · `curl https://hibs-bet.co.uk/fve-api/health`

## Trading micro deploy + revenue dashboard

Harvested Execution `/harvested-execution` shows PnL, promotion tier, and shadow progress.

**Micro install** (after shadow→micro scorecard GO):

```bash
sudo bash /opt/trading-core/deploy/install-harvested-execution-micro.sh
```

Sets `TRADING_METRICS_URL=http://127.0.0.1:9110` on hibs-bet. Caps: $100/order · $500 gross.

## Pre-push checklist (hibs-bet.co.uk)

### Must-do

- [ ] `pytest test_app.py -q tests/test_betting_strategy.py tests/test_assistant_features.py` — all green
- [ ] Server `.env` from `.env.example` (at minimum: `FOOTBALL_DATA_ORG_KEY`, `ODDS_API_KEY`; add `API_SPORTS_FOOTBALL_KEY` / `SPORTSMONK_KEY` if you use them)
- [ ] `HIBS_CACHE_DIR` set for production (systemd: `/opt/hibs-bet/.cache` in `hibs-bet.service`)
- [ ] After deploy: clear fixture cache for **v22** (dashboard Refresh or `POST /api/cache/clear`; delete stale `fixtures_*` / `all_fixtures_*` if needed)
- [ ] `sudo systemctl daemon-reload && sudo systemctl restart hibs-bet` (gunicorn **:8000**)

### Should-do

- [ ] `HIBS_PREDICTION_LOG_ENABLED=1` + `HIBS_CLV_LOG_ENABLED=1` (+ daily `pred-log-sync`, weekly `calibration-fit` via `deploy/cron-hibs-calibration.sh`)
- [ ] Scrape flags aligned with quota: `HIBS_MAX_DATA`, `HIBS_ENABLE_HEAVY_SCRAPERS`, `HIBS_ENABLE_FOTMOB_FIXTURES` (default on)
- [ ] Players dock: on by default (right rail); hide with `HIBS_SHOW_PLAYERS_DOCK=0`
- [ ] Optional Sky dock: `HIBS_SHOW_SKY_PANEL=1` (off by default); hides automatically if YouTube embed probe fails
- [ ] Deep enrich: safe production sets `HIBS_TARGET_DQ_PCT=90`, `HIBS_DEEP_ENRICH_TODAY_ONLY=1`, `HIBS_DEEP_ENRICH_MAX_RETRIES=2` (today’s fixtures only; stays within API budget)

### Nice-to-have (defer)

- [ ] Staging side-by-side on **:8001** (`hibs-bet-staging.service`)
- [ ] `HIBS_AUDIT_API_TOKEN` for `/api/audit/summary`
- [ ] Fit `calibration_v1.json` after enough logged results

### Do not

- Commit `.env`, `.env.txt`, or API keys
- Share production `.cache` with staging
