# Institutional++ failsafe operations

**Rule:** Engineering and automation must stay **green and non-degrading**. Evidence gaps (F8/F9 red) are **reported honestly** — never hidden, never auto-weakened.

Aligned with trading safety-first: **Reconciliation → Replay → Monitoring → Staged deploy → Model**.

---

## Priority stack (always)

| Layer | What | Failsafe behavior |
|-------|------|-------------------|
| **L0 Process** | `hibs-bet` systemd unit | `/api/ping` `ok:true`; restart throttled 45m/unit |
| **L1 Audit** | `prediction_audit.sqlite` | Logging on; pred-log-sync cron; never break predict pipeline |
| **L1b Settle** | FT + closing fallbacks | `HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK=1` — API-Sports → FDO → FotMob → ESPN backup FT; closing tagged honestly |
| **L2 Evidence** | F1–F9 gates | `safe_forward_evidence_gates()` — health never 500s on DB errors |
| **L3 Cohort** | Domestic trial F9 | `HIBS_F9_TRIAL_LEAGUES_ONLY=1`; WC/INTL excluded from pass cohort |
| **L4 Probes** | External monitors | `HIBS_AUTH_PUBLIC_HEALTH=1`; use `/api/ping` if auth blocks health |
| **L5 Automation** | Hands-off cycle | flock + rate limits; cron **exit 0** on evidence red |
| **L6 Repair** | Watchdog / 3-stack | Repair only with throttle; no API backfill from cron |

---

## One-shot VPS baseline

```bash
# From dev machine: rsync stack first (./scripts/deploy_vps_main_stack.sh)
cd /opt/hibs-bet
sudo bash scripts/vps_full_stack_100.sh
# or: sudo bash deploy/apply-vps-institutional-failsafe.sh --new-evidence-date
```

Sets: trial F9 cohort, public health probe, audit flags, hands-off crons, watchdog.

---

## Daily verify (30 seconds)

```bash
# On VPS
bash scripts/institutional_failsafe_verify.sh

# From Mac without SSH to app logs
HIBS_PRODUCTION_URL=https://hibs-bet.co.uk bash scripts/verify_production_probe.sh
```

Status JSON: `/var/log/hibs-bet/institutional-status.json`  
Hands-off: `/var/log/hibs-bet/hands-off-status.json`

---

## Kill switches

**Crash registry:** `deploy/football-inst-overlay/docs/VPS_FAILURE_MODES.md` — what keeps failing, cascade order, automation update checklist.

| Situation | Action |
|-----------|--------|
| Runaway restarts | `systemctl stop hibs-bet`; fix `.env`; restore prior git revision |
| Bad gate promote | Restore `.env` overlay; reset `HIBS_EVIDENCE_DEPLOY_DATE` |
| Trading recon drift | `systemctl stop trading-shadow-soak`; archive JSONL first |
| Automation storm | Remove hands-off cron line; check `/var/run/hibs-bet/*.lock` |

---

## CI / GitHub Actions

`stack-health.yml` every 6h:

1. **Public probe** — must pass (`/api/ping`)
2. **SSH repair** — skipped with warning if secrets missing (no false “total crash”)

Configure secrets for remote repair: `DEPLOY_HOST`, `DEPLOY_USER`, `SSH_PRIVATE_KEY`.

---

## Never do from automation

- Lower F9 thresholds or mix WC into trial pass cohort
- Unlimited service restart loops
- Live-capital / stake scale on red F9
- API odds backfill from cron (budget + nondeterministic)
- Disable audit to “green” the chip

---

## API-Sports lapse / scrape-first settlement

When `HIBS_DISABLE_API_SPORTS=1` (see `deploy/apply-vps-scrape-first.sh`), `pred-log-sync` still runs if scrape fallback is on:

| Step | Source | Notes |
|------|--------|-------|
| FT scores | Football-Data.org FINISHED | Needs `FOOTBALL_DATA_ORG_KEY` + league `football_data_org_id` |
| FT scores | FotMob daily matches | No key; team-name match on kickoff date |
| FT scores | FotMob ±1 day | Timezone edge cases |
| FT scores | ESPN scoreboard | `HIBS_SETTLE_BACKUP_ESPN=1` (default); cups/internationals when FotMob lags |
| FT scores | SofaScore events | `HIBS_SETTLE_BACKUP_SOFASCORE=1`; optional, often 403 on VPS |
| Closing 1X2 | API-Football odds | Only when API client still available |
| Closing 1X2 | The Odds API | Best-effort pre-kickoff lines |
| Closing 1X2 | `unavailable` | FT still settles; `clv.closing_source` records gap |

```bash
sudo -u www-data bash -c '
  set -a; source /opt/hibs-bet/.env; set +a
  export HOME=/opt/hibs-bet PYTHONPATH=/opt/hibs-bet/src
  cd /opt/hibs-bet
  .venv/bin/python -m hibs_predictor.main pred-log-sync --verbose
'
```

Verbose `sync_stats` keys: `resolved_football_data_org`, `resolved_fotmob`, `resolved_fotmob_adjacent`, `resolved_espn`, `resolved_sofascore`, `closing_*`.

Kill switch: `HIBS_AUDIT_SETTLE_SCRAPE_FALLBACK=0` restores API-Sports-only settlement (fails closed without key).

### VPS sync without Mac rsync (institutional)

Ad-hoc `curl` of single `.py` files drifts — use full-tree sync + env profile:

```bash
# 1) Full code from GitHub (pins branch; writes .deploy-revision)
sudo HIBS_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-from-github.sh

# 2) Scrape-first + MAX_DATA + deep enrich + ESPN settlement (data parity)
sudo bash /opt/hibs-bet/deploy/apply-vps-scrape-first-institutional.sh

# 3) Verify modules, env, ping
sudo bash /opt/hibs-bet/deploy/vps-verify-institutional.sh
```

Before PR merge, set `HIBS_SYNC_REF` to the feature branch. After merge, use `main`.

Mac rsync (`scripts/deploy_to_vps.sh`) remains the gold standard when SSH from dev machine works.

---

## Related

- [INSTITUTIONAL_SCORECARD.md](./INSTITUTIONAL_SCORECARD.md) — F1–F9 gates  
- [DOMESTIC_PROOF_AND_REBUILD_PLAN.md](./DOMESTIC_PROOF_AND_REBUILD_PLAN.md) — cohort + rebuild  
- [HANDS_OFF_AUTOMATION.md](./HANDS_OFF_AUTOMATION.md) — cron matrix  
