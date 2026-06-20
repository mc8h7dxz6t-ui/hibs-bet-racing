# Full-platform automation export

Use when `/opt/hibs-bet` is on **main** and missing `install_all_platform_automation.sh`.

## Fastest path on VPS (87.106.100.52)

```bash
cd /opt/hibs-bet
sudo git pull origin main 2>/dev/null || true

# Option A — bootstrap from this export (after PR merge to hibs-bet-racing):
curl -fsSL "https://raw.githubusercontent.com/mc8h7dxz6t-ui/hibs-bet-racing/cursor/full-platform-automation-export-7e4d/docs/export-full-platform-automation/bootstrap-vps.sh" | bash

# Option B — if you have the repo clone on the VPS already:
sudo bash /path/to/docs/export-full-platform-automation/bootstrap-vps.sh
```

## Manual copy (works right now without curl)

If the export folder is on the server under `/tmp/export`:

```bash
sudo install -m 755 /tmp/export/scripts/*.sh /opt/hibs-bet/scripts/
sudo install -m 755 /tmp/export/deploy/*.sh /opt/hibs-bet/deploy/
sudo bash /opt/hibs-bet/scripts/install_all_platform_automation.sh --skip-sync
```

## What `install_all_platform_automation.sh` does

1. `stack.env` — FVE on localhost
2. Engineering grade A env + trial cohort
3. All www-data crons (audit, fixture warm, hands-off 30m, racing, trading)
4. www-data sudoers for repair cycle
5. Immediate fixture warm + data producer repair
6. Hands-off cycle (don't wait 30 minutes)

## Football still empty?

Automation runs every 3h but **needs a fixture source** in `.env`:

```bash
grep -E 'FOOTBALL_DATA_ORG_KEY|HIBS_DISABLE_API_SPORTS|API_FOOTBALL' /opt/hibs-bet/.env
sudo HIBS_FIXTURE_WARM_FORCE_REFRESH=1 bash /opt/hibs-bet/scripts/warm_football_fixtures.sh
tail -30 /var/log/hibs-bet/fixture-warm.log
```

## Verify crons armed

```bash
crontab -u www-data -l | grep hibs
tail -20 /var/log/hibs-bet/hands-off-cycle.log
bash /opt/hibs-bet/scripts/verify_inst_pp_automation.sh
```
