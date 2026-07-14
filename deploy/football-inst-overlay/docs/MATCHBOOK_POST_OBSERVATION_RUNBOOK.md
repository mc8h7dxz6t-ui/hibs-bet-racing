# Matchbook — post-observation go-live runbook

Fund and wire Matchbook **after** the racing observation lane ends (formal gate **2026-06-19** per `MASTER_OPERATIONS_SCORECARD.md` §3). Two lanes share the same exchange account but different code paths:

| Lane | Repo | What funding unlocks | Live orders? |
|------|------|----------------------|--------------|
| **Racing odds** | hibs-bet-racing | API access ($200 min balance) + daily GB/IRE quote ingest | **No** — `EXECUTION_DISABLED = True` (analytics + paper ledger only) |
| **FVE arb** | football-app on FVE VPS | Exchange poll + optional micro-stake arb | **Yes** — only after arb ladder stage 3 |

---

## Prerequisites (before you deposit)

1. Observation lane produced clean daily batches (`preflight_observation_lane.sh` GREEN).
2. Paper ledger has settling rows (institutional recon not blocking).
3. Matchbook API access email answered (`hibs-bet-racing/docs/MATCHBOOK_API_REQUEST.md`).

---

## Step 1 — Fund the account

- Deposit **≥ $200** (or GBP equivalent) on [matchbook.com](https://www.matchbook.com).
- Wait for Matchbook to enable API access (reply to `api@matchbook.com` if session login fails after funding).

---

## Step 2 — Local preflight (Mac)

```bash
cd ~/hibs-bet
git pull
bash scripts/preflight_matchbook_funded.sh ~/hibs-racing/.env --require-funded --probe-edge
```

Exit **0** = session + balance OK · **non-zero** = fix creds, location, or funding first.

Full stack audit:

```bash
bash scripts/matchbook_post_observation_readiness.sh
```

Exit **0** = GREEN · **2** = partial (warnings) · **1** = blocked.

---

## Step 3 — Racing: exit observation lane

Observation used `HIBS_OBSERVATION_LANE=1` (softer gates). After the gate:

```bash
cd ~/hibs-racing
bash scripts/preflight_matchbook_post_observation.sh
```

When GREEN, set in `.env`:

```bash
HIBS_OBSERVATION_LANE=0
```

Re-run institutional check (production thresholds — Matchbook coverage ≥50%):

```bash
hibs-racing institutional-check --days 14 --card-date "$(date -u +%F)"
```

**Do not** enable live exchange routing in racing — execution stays off by design (`execution_config.py`).

---

## Step 4 — Sync credentials to VPS

On Mac, ensure `~/hibs-racing/.env` has `MATCHBOOK_USER` / `MATCHBOOK_PASSWORD`.

On **main VPS** (`77.68.89.73`):

```bash
sudo bash /opt/hibs-bet/deploy/apply-vps-matchbook-env-sync.sh
```

To also push creds to the **FVE box** (`77.68.89.75`):

```bash
sudo FVE_REMOTE_HOST=77.68.89.75 FVE_DEPLOY_PATH=/opt/football-app \
  bash /opt/hibs-bet/deploy/apply-vps-matchbook-env-sync.sh
```

Then recover racing value lane:

```bash
sudo bash /opt/hibs-bet/scripts/vps_racing_value_lane_recovery.sh
```

---

## Step 5 — FVE arb ladder (football — optional micro-live)

See `football-app/docs/ARB_FREEZE.md`. **Never skip stages.**

| Stage | Env | Action |
|-------|-----|--------|
| **1 Shadow** | `FVE_ARB_ONLY=1`, `MATCHBOOK_KILL_SWITCH=1`, `FVE_PAUSED=1` | `docker compose --profile arb-shadow up -d` |
| **2 Dry-run** | `MATCHBOOK_KILL_SWITCH=0`, `MATCHBOOK_AUTO_TRADE=0` | Executor builds offers, no submit |
| **3 Micro-live** | `MATCHBOOK_AUTO_TRADE=1`, `MATCHBOOK_CONFIRM_LIVE=YES` | Caps: `MATCHBOOK_MAX_STAKE=2`, `MATCHBOOK_MAX_OUTLAY=6` |

Audit current stage:

```bash
cd ~/football-app
bash scripts/preflight_matchbook_arb_stage.sh
```

Micro-live requires funded balance **and** explicit `MATCHBOOK_CONFIRM_LIVE=YES` on the FVE host only.

---

## Kill switches

| Product | How to stop |
|---------|-------------|
| Racing odds poll | Remove Matchbook creds from `.env` or stop `daily_refresh` cron |
| FVE arb | `MATCHBOOK_KILL_SWITCH=1` or `bash scripts/pause_fve.sh` |
| All Matchbook | Withdraw / disable API at Matchbook account level |

---

## What this does **not** do

- Does not flip `buyer_ready` — evidence gates (F7–F9, R5–R7) still apply.
- Does not enable racing live bets — paper + affiliate only.
- Does not guarantee arb PnL — cross-book arbs may be partial-dutch blocked unless `MATCHBOOK_ALLOW_PARTIAL_DUTCH=1`.

---

## Related docs

- `docs/MASTER_OPERATIONS_SCORECARD.md` §3 — observation lane
- `hibs-bet-racing/docs/MATCHBOOK_API_REQUEST.md` — API application
- `football-app/docs/ARB_FREEZE.md` — arb ladder
- `scripts/test_matchbook_credentials.sh` — quick login probe (no balance gate)
