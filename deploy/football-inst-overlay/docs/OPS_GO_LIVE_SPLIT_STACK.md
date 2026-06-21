# Split-stack go-live runbook

Get all three platforms running for observation. Run from your Mac (or any host with SSH to both VPSes).

## Prerequisites

| Step | Where | Action |
|------|-------|--------|
| 1 | Provider panel | Attach **20GB block volume** to `77.68.89.73` (main) |
| 2 | Provider panel | Attach **20GB block volume** to `77.68.89.75` (FVE) |
| 3 | Both VPSes | `lsblk` — note device (usually `/dev/sdb`) |
| 4 | Main `.env` | API keys, `HIBS_AUTH_PASSWORD` already set |

## Order of operations

**Do FVE box first**, then main VPS (main nginx needs FVE up for line-trader).

### A. FVE box (`77.68.89.75`) — ~15 min

```bash
ssh root@77.68.89.75
lsblk   # confirm /dev/sdb exists

curl -fsSL https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet/main/deploy/ops-bootstrap-fve-vps.sh | sudo \
  VOLUME_DEVICE=/dev/sdb \
  HIBS_MAIN_IP=77.68.89.73 \
  HIBS_UPSTREAM_BASE_URL=https://hibs-bet.co.uk \
  HIBS_FVE_RAW_BRANCH=main \
  bash

# Verify before leaving
curl -sS http://127.0.0.1:8010/health | python3 -m json.tool | head -20
```

### B. Main VPS (`77.68.89.73`) — ~20 min

```bash
ssh root@77.68.89.73
lsblk   # confirm /dev/sdb exists

curl -fsSL https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet/main/deploy/ops-bootstrap-main-vps.sh | sudo \
  HIBS_SYNC_REF=main \
  HIBS_RACING_SYNC_REF=main \
  VOLUME_DEVICE=/dev/sdb \
  FVE_REMOTE_HOST=77.68.89.75 \
  HIBS_PUBLIC_HOST=hibs-bet.co.uk \
  bash
```

This single script:

1. Syncs **hibs-bet** + **hibs-racing** from GitHub `main`
2. Mounts racing SQLite on block storage (`/mnt/hibs-racing-data`)
3. Applies scrape-first institutional env (no API quota burn)
4. Wires nginx racing + trading + FVE remote proxy
5. Installs all evidence crons (daily audit, racing refresh, watchdog)
6. Prints observation summary

### C. Trading (if not already on main VPS)

```bash
ssh root@77.68.89.73
sudo bash /opt/hibs-bet/deploy/install-harvested-execution-shadow.sh
sudo bash /opt/hibs-bet/deploy/apply-vps-trading-link.sh
sudo bash /opt/hibs-bet/deploy/apply-trading-rest-fallback.sh   # optional: HTTP tape backup
```

## Observe

```bash
# On main VPS — repeat anytime
sudo bash /opt/hibs-bet/deploy/ops-observe-stack.sh
```

**Browser:**

| URL | What to watch |
|-----|----------------|
| https://hibs-bet.co.uk/ | Football picks + product bar |
| https://hibs-bet.co.uk/racing/ | Racing cards + paper ledger |
| https://hibs-bet.co.uk/line-trader | FVE lines (remote 1GB box) |
| https://hibs-bet.co.uk/harvested-execution | Trading shadow ops |

**Logs:**

```bash
journalctl -u hibs-bet -f
journalctl -u hibs-racing -f
tail -f /var/log/hibs-bet/three-stack-green.log
tail -f /var/log/fve/lines-collector.log   # on FVE box
```

## What builds over time (crons)

| Evidence | Cron | Typical timeline |
|----------|------|------------------|
| Football F7–F9 | daily audit + pred-log-sync | days–weeks |
| Racing R7 paper rows | racing daily refresh 06:05 UTC | days |
| Trading shadow 30d | trading-shadow-soak running | 30 days |
| CLV beat-close 28d | settles as fixtures complete | rolling 28d |

## Re-sync after code changes

```bash
# Main only
sudo HIBS_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-from-github.sh
sudo HIBS_RACING_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-racing-from-github.sh
sudo bash /opt/hibs-bet/deploy/apply-vps-scrape-first-institutional.sh

# FVE box
ssh root@77.68.89.75
cd /opt/fve && git pull origin main && docker compose up -d --build
```

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| Line-trader 404 | `sudo FVE_REMOTE_HOST=77.68.89.75 bash /opt/hibs-bet/deploy/apply-vps-fve-remote-host.sh` |
| FVE unreachable from main | Check ufw on FVE: port 8010 from 77.68.89.73 only |
| Racing 502 | `bash /opt/hibs-bet/scripts/vps_racing_hard_recovery.sh` |
| Full stack repair | `bash /opt/hibs-bet/scripts/vps_three_stack_green.sh --repair` |
