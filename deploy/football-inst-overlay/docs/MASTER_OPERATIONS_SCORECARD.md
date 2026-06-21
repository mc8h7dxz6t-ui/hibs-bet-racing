# Master Operations Scorecard

**Scope:** Home operations matrix — football (hibs-bet), trading (Harvested Execution), racing (placeholder).  
**Rule:** Pass/fail only. No config changes during active gates unless a gate explicitly fails.

| Product | Launch / decision date | Detail doc |
|---------|------------------------|------------|
| **Football** | **2026-06-11** World Cup launch | [INSTITUTIONAL_SCORECARD.md](./INSTITUTIONAL_SCORECARD.md) · [DOMESTIC_PROOF_AND_REBUILD_PLAN.md](./DOMESTIC_PROOF_AND_REBUILD_PLAN.md) |
| **Trading** | **2026-06-18** Day-15 line in the sand | [TRADING_PROMOTION_SCORECARD.md](./TRADING_PROMOTION_SCORECARD.md) |
| **Racing** | **2026-06-04 → 10** observation lane; **2026-06-19** formal gate | §3 below (local daily batch only) |

---

## 0. Daily command (30 seconds)

```bash
# Football (VPS)
curl -sS http://127.0.0.1:5000/api/health | python3 -c "import sys,json;d=json.load(sys.stdin);ao=d.get('audit_ops',{});print('1X2',ao.get('odds_capture',{}).get('capture_rate_pct'),'% cron',ao.get('pred_log_sync_cron',{}).get('scheduled'))"

# Trading (VPS — frozen config, port 9108)
ssh root@77.68.89.73 'systemctl is-active trading-shadow-soak; curl -s http://127.0.0.1:9108/live'

# Racing (local host — daily batch cron)
crontab -l 2>/dev/null | grep -q 'daily_refresh.sh' && echo 'racing cron: ON' || echo 'racing cron: OFF'
tail -1 ~/hibs-racing/logs/cron_daily.log 2>/dev/null || true
```

---

## 1. Football — GO for 2026-06-11 World Cup

**Frozen from:** deploy date through launch week. **No** trading deploys, **no** racing work that steals VPS/API budget.

### Critical (any FAIL → no WC launch promotion / no stake scale)

| ID | Pass | Fail | Check |
|----|------|------|-------|
| F1 | `HIBS_PREDICTION_LOG_ENABLED=1` | off | `PYTHONPATH=src python3 -m hibs_predictor.main institutional-check` |
| F2 | `HIBS_CLV_LOG_ENABLED=1` | off | same |
| F3 | Cron scheduled | `needs_reminder` | `/api/health` → `audit_ops.pred_log_sync_cron.scheduled=true` |
| F4 | `pytest` green | any fail | `PYTHONPATH=src python3 -m pytest tests/ -q` |
| F5 | `HIBS_PRODUCTION=1`, no `HIBS_DEV_FULL_DQ` | blocking | `python3 scripts/validate_institutional_config.py` |
| F6 | `hibs-bet` active on VPS | down | `systemctl is-active hibs-bet` |

### Evidence (FAIL → launch allowed, **no stake scale** on value ROI)

| ID | Pass | Fail | Check |
|----|------|------|-------|
| F7 | Forward 1X2 capture **≥ 50%** (rolling 7d, after ≥3 matchdays post-deploy) | &lt;50% | `/api/health` → `audit_ops.odds_capture.capture_rate_pct` |
| F8 | `clv_beat_close_28d.n_clv_rows` **≥ 25** | &lt;25 | `/api/health` → `clv_beat_close_28d` |
| F9 | CLV beat-close **≥ 50%** on those rows | below | `beat_close_pct` |

### Pre-launch deploy (once, before 2026-06-11)

```bash
cd /opt/hibs-bet && git pull origin main
sudo bash deploy/apply-vps-safe-production.sh
sudo bash deploy/apply-vps-trial-production.sh
sudo systemctl restart hibs-bet
sudo bash deploy/cron-hibs-calibration.sh --install
```

**UI:** Dashboard / Players → top-right **Audit · 1X2** chip (amber if &lt;50%). `/status#audit-evidence`.

---

## 2. Trading — annex (hands off until 2026-06-18)

**Status (2026-06-05):** Institutional dual-feed: **Alpaca IEX (AAPL)** + **Coinbase public WSS (BTC/USD)** on one Alpaca key. See [TRADING_DUAL_FEED_INSTITUTIONAL.md](./TRADING_DUAL_FEED_INSTITUTIONAL.md). Gate A/B: `scripts/compare_trading_gate_profiles.py`.

**Frozen until 2026-06-18:** No OFI threshold tuning, no promotion to micro/live. **Allowed:** dual-feed deploy + orchestrator restart.

```bash
ssh root@77.68.89.73 'sudo systemctl restart trading-shadow-soak'
curl -s http://127.0.0.1:9108/ready   # finite stale_feed_equity_ms + stale_feed_crypto_ms in RTH
python3 scripts/compare_trading_gate_profiles.py --audit data/strategy_scan_shadow_calibration.jsonl
```

### Day-15 decision line (2026-06-18) — AAPL equity lane only

Pull artifacts:

```bash
ssh root@77.68.89.73 'wc -l /opt/trading-core/data/strategy_scan_shadow_calibration.jsonl /opt/trading-core/data/spread_slippage_shadow_calibration.jsonl'
```

| Verdict | Condition | Action |
|---------|-----------|--------|
| **PASS** | ≥1 `SHADOW_WOULD_ROUTE` on **AAPL** **and** spread JSONL shows would-route `|delta_bps|` p95 **≤ max(15, ASSUMED_SPREAD_BPS + 5)** | Proceed to [TRADING_PROMOTION_SCORECARD.md](./TRADING_PROMOTION_SCORECARD.md) shadow→micro path; fix crypto lane (second Alpaca data key preferred) before BTC capital |
| **FAIL** | No would-route rows **or** p95 slippage systematically worse than threshold **or** repeated recon drifts | Archive telemetry (§2.1), then hard stop (§2.2); **no micro-live**; pivot ops focus to football/racing |
| **INCONCLUSIVE** | &lt;3 matchdays of equity stream data | Extend shadow 7d only; still no live capital |

### 2.1 FAIL — archive evidence (data room)

Run **before** stopping the service. Preserves JSONL for FinTech portfolio / post-mortem.

```bash
# Stage 1: Compress and timestamp raw slippage and scan logs
ssh root@77.68.89.73 'tar -czf /tmp/trading-shadow-evidence-$(date +%F).tar.gz -C /opt/trading-core/data strategy_scan_shadow_calibration.jsonl spread_slippage_shadow_calibration.jsonl shadow_soak_audit.log harvested_execution_engine.jsonl'
```

Copy off-box: `scp root@77.68.89.73:/tmp/trading-shadow-evidence-*.tar.gz ~/Archive/`

### 2.2 FAIL — hard stop (after archive)

```bash
# Stage 2: Stop soak and disable autostart (no restart on reboot)
ssh root@77.68.89.73 'sudo systemctl stop trading-shadow-soak && sudo systemctl disable trading-shadow-soak'
```

**PASS path:** do **not** run §2.2; continue shadow per [TRADING_PROMOTION_SCORECARD.md](./TRADING_PROMOTION_SCORECARD.md).

**Automated check (after soak):**

```bash
python3 scripts/evaluate_promotion_scorecard.py \
  --transition shadow_to_micro \
  --evidence-daily-dir data/evidence/daily \
  --metrics-url http://127.0.0.1:9108 \
  --output-md data/evidence/promotion_scorecard.md
```

Exit **0 = GO**, **1 = NO-GO** for promotion mechanics; **Day-15 economic PASS/FAIL** is the AAPL slippage table above.

**Out of scope until PASS:** Multiplexer refactor, micro/live caps, live Alpaca URL.

---

## 3. Racing — observation lane (2026-06-04 → 2026-06-10)

**Amended from quarantine:** Forward **data collection only** during peak UK summer cards. **No code, no model retrain, no VPS deploy, no intraday polling.**

| Rule | Detail |
|------|--------|
| Priority | Football WC launch (11 Jun) + trading shadow soak (18 Jun) unchanged |
| Allowed | **Daily batch only** — existing `scripts/daily_refresh.sh` on **local host** (repo `~/hibs-racing`) |
| Blocked | Code changes, `weekly_retrain.sh`, `intraday_poll_30m.sh`, new Matchbook/Betfair integration, **VPS racing deploy**, nginx `/racing/` proxy |
| First formal gate | **2026-06-19** — racing promotion scorecard or defer to Q3 |

**Inst++ data producer SLO:** `scripts/data_producer_repair.sh` + `/api/health?light=1` — automated in `hands_off_cycle.sh` every 30m.

**Post-gate Matchbook funding:** see `docs/MATCHBOOK_POST_OBSERVATION_RUNBOOK.md` — `preflight_matchbook_funded.sh`, `matchbook_post_observation_readiness.sh`, VPS `apply-vps-matchbook-env-sync.sh`. `77.68.89.73` has trading shadow + football only — no `/opt/hibs-racing`, no racing cron, no `hibs-racing-daily-refresh.timer` unit. VPS check: `hibs-bet` + `trading-shadow-soak` **active**; racing **absent**.

### 3.0 Live audit (2026-06-03 — verify, do not reinstall blindly)

| Check | Status |
|-------|--------|
| Local daily cron | **Already ON** — `0 6 * * * …/daily_refresh.sh >> …/logs/cron_daily.log` |
| `weekly_retrain.sh` | **Frozen** — must stay commented out / absent from crontab |
| Log path | **`~/hibs-racing/logs/cron_daily.log`** — not `data/logs/daily_cron.log` |
| Mac scheduler | Cron fires only if Mac is **awake** at 06:00 Europe/London; confirm Energy Saver / sleep settings |
| Last cron run | **2026-06-03 failed** mid-pipeline (`daily-refresh-cards`) — lane is **not green** until one full smoke passes |
| Matchbook dry-run | Creds OK; coverage can be **low** (~13% on evening sample) — venue pairing noise is expected evidence, not a freeze violation |

**Gate before “step away”:** `bash scripts/daily_refresh.sh` must reach `Daily refresh completed successfully.` Recon-only FAIL at tail is acceptable on day 1; card refresh FAIL is not.

### 3.1 Pre-flight (once, before enabling cron)

```bash
cd ~/hibs-racing && bash scripts/preflight_observation_lane.sh
# Morning activation gate (after 06:00 UK cards):
bash scripts/preflight_observation_lane.sh --smoke
```

Exit **0** = armed · **2** = armed with warnings (off-hours) · **1** = blocked.

See §3.6 if card refresh fails twice with the same runtime error.

**Day-1 expectation:** `daily_refresh.sh` ends with `institutional-check --require-recon-clean`. First runs may **FAIL recon** until paper ledger + SP settlement populate — that is evidence gap, not a reason to patch code during the freeze.

### 3.2 Enable daily batch only (correct command)

**Do not** run `scripts/install_cron.sh` wholesale — it also installs **Sunday `weekly_retrain.sh`** (model retrain = violates freeze).

**Do not** use `systemctl enable hibs-racing-daily-refresh.timer` — that unit **does not exist** in this repo.

Install **daily line only** (06:00 **Europe/London** — adjust if server TZ differs):

```bash
cd ~/hibs-racing
chmod +x scripts/daily_refresh.sh scripts/_lib.sh
mkdir -p logs
( crontab -l 2>/dev/null | grep -v 'hibs-racing/scripts/daily_refresh.sh' | grep -v 'hibs-racing/scripts/weekly_retrain.sh'; \
  echo "0 6 * * * $(pwd)/scripts/daily_refresh.sh >> $(pwd)/logs/cron_daily.log 2>&1" ) | crontab -
```

One-shot smoke (optional, tonight):

```bash
cd ~/hibs-racing && bash scripts/daily_refresh.sh
```

### 3.3 What runs automatically (daily batch)

| Step | Artifact |
|------|----------|
| Ingest + card refresh | GB/IRE cards via Racing API, LightGBM score, actionability gates |
| `--paper` | Production-lane value picks → `data/feature_store.sqlite` |
| Matchbook baseline poll | `exchange_quotes` table (`HIBS_POLL_MILESTONE=baseline`) |
| **Telemetry balance** | `telemetry_balance` ledger event + `/api/health` — Racing API fetch vs Matchbook odds share, coverage ≥35% (obs) / 50% (prod), total_ms SLA |
| Afternoon settle | SP join + execution slippage via same daily script chain |

**Not automatic from daily cron alone:**

| Item | How to get it |
|------|----------------|
| `reports/weekly_gate_efficacy.md` | **Sunday ops only** (manual): `cd ~/hibs-racing && bash scripts/weekly_gate_efficacy.sh` — or `HIBS_WEEK_ENDED=2026-06-07 bash scripts/weekly_gate_efficacy.sh` on **2026-06-08** after the week’s cards settle |
| Pre-race 30m polls | `intraday_poll_30m.sh` — **stay off** until post-WC gate |
| Model retrain | `weekly_retrain.sh` — **stay off** until post-WC gate |

### 3.4 API budget / conflict check

| Consumer | Jun 3–10 load |
|----------|----------------|
| Football (VPS) | Low — no WC matches yet; cron/health only |
| Trading shadow (VPS) | Alpaca WSS — isolated from racing |
| Racing (local) | Racing API + Matchbook **once/day** — acceptable if pre-flight creds green |

### 3.5 Kill switch

```bash
crontab -l | grep -v 'hibs-racing/scripts/daily_refresh.sh' | crontab -
```

### 3.6 Freeze exception (card-refresh runtime only)

If full smoke (`bash scripts/daily_refresh.sh`) fails at **`daily-refresh-cards`** with the same error twice (e.g. `boolean value of NA is ambiguous`), a **minimal hotfix** in the card-ingest / data-quality path is permitted.

| Allowed | Blocked |
|---------|---------|
| NA / null-safe parsing in ingest or gate prep | LightGBM retrain, gate threshold changes, Matchbook venue-map work, VPS deploy |
| One focused fix + `pytest tests/test_actionability.py tests/test_institutional_hardening.py -q` | Scope creep into football or trading repos |

**Lane armed:** smoke reaches `Daily refresh completed successfully.` (recon-only FAIL at institutional tail still OK on day 1).

### 3.7 Mac sleep (06:00 cron reliability)

macOS cron does **not** wake a sleeping machine. During Jun 4–10 pick one:

| Option | Action |
|--------|--------|
| **A — plugged in** | System Settings → Energy: prevent sleep on power adapter overnight |
| **B — manual fallback** | On wake each morning: `cd ~/hibs-racing && bash scripts/daily_refresh.sh` (check `logs/cron_daily.log` for missed days) |

Detail (when active): separate racing scorecard doc; do not merge into football or trading gates.

---

## 4. Cross-product kill switches

| Product | Stop command |
|---------|--------------|
| Football | `sudo systemctl stop hibs-bet` |
| Trading shadow (FAIL only) | Archive §2.1, then `ssh root@77.68.89.73 'sudo systemctl stop trading-shadow-soak && sudo systemctl disable trading-shadow-soak'` |
| Trading paper | `ssh root@77.68.89.73 'sudo systemctl stop trading-paper'` |
| Racing daily (observation) | `crontab -l \| grep -v 'hibs-racing/scripts/daily_refresh.sh' \| crontab -` |

---

## 5. Sign-off (paste when closing a gate)

```
Gate: FOOTBALL_WC_2026-06-11 / TRADING_DAY15_2026-06-18
Date: ___________
Critical IDs: ___________
Evidence IDs: ___________
Operator: ___________
Verdict: GO / NO-GO / LAUNCH_NO_STAKE_SCALE
Notes: ___________
```

---

## Related

- [INSTITUTIONAL_SCORECARD.md](./INSTITUTIONAL_SCORECARD.md) — football engineering + evidence  
- [TRADING_PROMOTION_SCORECARD.md](./TRADING_PROMOTION_SCORECARD.md) — staged trading rollout  
- [TRADING_EVIDENCE_RUNBOOK.md](./TRADING_EVIDENCE_RUNBOOK.md) — daily trading evidence  
- `.cursor/rules/trading-safety-first.mdc` — trading safety priority order
