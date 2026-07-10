# Sports-only operations — football + racing

**Ignore:** governors, Inst++ nine-ten, Phase D regulatory matrices.

---

## Your VPS status (from your paste)

| Item | Status |
|------|--------|
| Football cache | **GREEN** — 19 fixtures, ping 200 |
| F1–F3 | **PASS** |
| F7–F9 | **FAIL** — `matchdays_7d: 0` (summer gap — expected) |
| **Crontab** | **BROKEN** — ~3283 lines, install fails at 10k limit |
| `install-hibs-cron-sudoers.sh` | Missing until overlay synced |
| Racing | Use observation cron during freeze (no weekly retrain) |

---

## EMERGENCY FIRST — fix crontab (do not re-run ops-automation until done)

```bash
# 1) Sync overlay from hibs-bet-racing (if /opt/hibs-racing has the repo)
sudo OVERLAY_ROOT=/opt/hibs-racing/deploy/football-inst-overlay \
  bash /opt/hibs-racing/deploy/vps-sync-football-inst-overlay.sh

# 2) Replace bloated crontab with sports-only (~12 lines)
sudo bash /opt/hibs-bet/deploy/crontab-emergency-sports-only.sh

# 3) Confirm
crontab -u www-data -l | wc -l    # should be < 20
crontab -u www-data -l | grep hibs-bet

# 4) Sudoers for hands-off (after overlay)
sudo bash /opt/hibs-bet/deploy/install-hibs-cron-sudoers.sh
```

**Do not** run `cron-hibs-ops-automation.sh --install` again until line count is normal.

---

## Football (`/opt/hibs-bet`)

### Sync code (hibs-bet repo on GitHub)

```bash
cd /opt/hibs-bet
sudo bash deploy/vps-sync-from-github.sh
```

If sync runs **stack wiring cache bust** while bundle is already OK (19 fixtures), **Ctrl+C** after ping is green — bust destroys good cache.

### Daily automation (after emergency crontab)

| UTC | Job |
|-----|-----|
| 06:35 | Daily audit + pred-log-sync |
| 23:05 | Evening audit + sync |
| 06:25 + */3h | Fixture warm |
| 12:05, 22:30, 23:45 | Cross-platform results |
| 07:35, 14:35 | Seed forward snapshots (matchdays) |

### Verify

```bash
bash /opt/hibs-bet/scripts/verify_football_evidence_gates.sh
curl -s http://127.0.0.1:8000/api/ping | python3 -m json.tool | head -5
```

### Matchdays only

```bash
bash /opt/hibs-bet/scripts/run_forward_backfill_plan.sh
```

---

## Racing (`/opt/hibs-racing`)

### Observation freeze (no weekly retrain)

```bash
cd /opt/hibs-racing
bash scripts/install_observation_cron.sh
```

This installs **daily 06:00 local only** via `cron_refresh_wrapper.sh` — **not** `weekly_retrain.sh`.

### Verify

```bash
bash /opt/hibs-racing/scripts/daily_refresh.sh          # smoke once
bash /opt/hibs-racing/scripts/verify_racing_evidence_gates.sh
tail -50 /opt/hibs-racing/logs/cron_daily.log
```

### Services

```bash
sudo systemctl enable --now hibs-bet
sudo systemctl enable --now hibs-racing   # if unit exists
```

---

## What to skip (sports-only)

- `verify_inst_pp_automation.sh` — Inst++ cron markers (optional)
- `cron-hibs-ops-automation.sh --install` — use emergency script instead until fixed
- Nine-ten / institutional watchdog / calibration drift crons
- Governor / Phase D / examiner packs

---

## Honest expectations

- **Running:** football predictions + racing cards with cron refresh.
- **Not green yet:** F7–F9 until domestic matchdays return and snapshots accumulate.
- **Not claimed:** enterprise platform, buyer_ready = PE-ready, regulatory compliance.

See [compliance/claims-today-vs-blocked.md](compliance/claims-today-vs-blocked.md).
