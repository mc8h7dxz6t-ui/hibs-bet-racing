# Hands-Off 10/10 — VPS operator runbook

Industry target: **unattended infra GREEN** with paper/shadow execution, evidence gates, and optional live staking behind explicit env flags.

## What 10/10 means here

| Tier | Definition | Default |
|------|------------|---------|
| **Infra 10/10** | Football + racing ping 200, systemd active, 5m fallback + 30m hands-off + hourly Brier crons | **Target today** |
| **Paper 10/10** | Daily refresh, paper ledger, shadow intents, pre-race steam poll | **Target today** |
| **Live execution** | Matchbook offers with slippage guard | **OFF** until `HIBS_EXECUTION_LIVE=1` + evidence GREEN |

Live funded staking is intentionally **not** the default — analytics license + calibration safety first.

## One-shot arm (after sync)

```bash
sudo HIBS_RACING_SYNC_REF=main \
  bash /opt/hibs-racing/deploy/football-inst-overlay/deploy/vps-sync-racing-from-github.sh
sudo HIBS_OVERLAY_SKIP_WARM=1 \
  bash /opt/hibs-racing/deploy/football-inst-overlay/deploy/vps-sync-football-inst-overlay.sh

sudo bash /opt/hibs-bet/deploy/install-hibs-cron-sudoers.sh
sudo bash /opt/hibs-bet/deploy/cron-hibs-ops-automation.sh --install
sudo bash /opt/hibs-bet/scripts/vps_industry_standard_run.sh --repair
```

Overlay sync now auto-installs: infra fallback (5m), Brier circuit (hourly), sudoers refresh.

## Verify

```bash
bash /opt/hibs-bet/scripts/verify_vps_relative_paths.sh
bash /opt/hibs-bet/scripts/verify_public_edge.sh
bash /opt/hibs-bet/scripts/verify_execution_readiness.sh
bash /opt/hibs-bet/scripts/verify_personal_staking_greenlights.sh --json
curl -fsS http://127.0.0.1:8000/api/ping
curl -fsS http://127.0.0.1:5003/api/ping
```

## Full stack recovery (502 / unarmed automation)

```bash
sudo bash /opt/hibs-bet/scripts/vps_full_stack_recovery.sh
```

See `docs/ORDERED_RECOVERY_RUNBOOK.md` for phased manual recovery.

## Cron bundle (www-data)

| Job | Schedule | Purpose |
|-----|----------|---------|
| infra fallback | `*/5` | 502 probe → soft/hard recovery |
| Brier circuit | `5 * * *` | Calibration lockout FSM |
| hands-off | `*/30` | Stack repair + data producer |
| racing daily | `5 6 * *` | Cards, odds, paper settle |
| pre-race poll | `*/2` (08–20 UTC) | Steam/drift via Matchbook |
| fixture warm | `*/3h` | Football cache headless |
| low-source scrape | `*/2h` | Scrape-first enrichment |

## Pip corruption (`~ibs-racing`)

```bash
sudo bash /opt/hibs-bet/scripts/repair_racing_venv_pip.sh
```

## Crontab emergency (>200 lines)

```bash
sudo bash /opt/hibs-bet/deploy/crontab-emergency-sports-only.sh
sudo bash /opt/hibs-bet/deploy/cron-hibs-ops-automation.sh --install
```

## Enabling live execution (racing only — manual gate)

1. Evidence GREEN: R5–R8 + personal staking
2. Brier circuit CLOSED on both domains
3. Set in `/opt/hibs-racing/.env`: `HIBS_EXECUTION_LIVE=1`
4. Code change required: `EXECUTION_DISABLED` env gate (not flipped by default)
5. `HIBS_REQUIRE_LIVE_EXECUTION=1 bash verify_execution_readiness.sh` must pass

Football remains **signals-only** until a bookmaker execution router exists.

## Architecture docs

- `docs/INGRESS_CALIBRATION_SAFETY.md` — OddsPapi, Brier FSM, Redis, WAL
- `docs/VPS_FAILURE_MODES.md` — FM-01–FM-07 crash registry
