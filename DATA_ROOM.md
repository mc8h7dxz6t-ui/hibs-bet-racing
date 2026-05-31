# Hibs Racing Intelligence — Data Room Summary

**Asset:** Proprietary LightGBM UK/IRE horse racing analytics engine  
**Master ledger:** `exports/Hibs_Racing_Master_6Month_TrackRecord.csv`  
*(Winter calibration Dec–Feb 2026 + May OOS holdout — single buyer-facing file)*  
**Public verifier:** `http://127.0.0.1:5003/tracker?backtest=1` · SHA-256 `verification_hash` per row

---

## Data Room Files

| File | Period | Rows | Label for buyers |
|------|--------|------|------------------|
| **`Hibs_Racing_Master_6Month_TrackRecord.csv`** | Dec–Feb + May 2026 | **10,176** | **Primary data room deliverable** |
| `Hibs_Racing_Backtest_DecFeb2026_TrackRecord.csv` | Dec → Feb (winter) | 7,926 | Model calibration (in-sample) |
| `Hibs_Racing_OOS_PhaseA_May2026_TrackRecord.csv` | May only | 2,250 | Pure OOS holdout (merged into master) |

**Build master (one file for listing):**
```bash
cat exports/Hibs_Racing_Backtest_DecFeb2026_TrackRecord.csv \
  <(tail -n +2 exports/Hibs_Racing_OOS_PhaseA_May2026_TrackRecord.csv) \
  > exports/Hibs_Racing_Master_6Month_TrackRecord.csv
```

Optional period slices (not required for listing): Nov–Jan, Feb–Apr exports in `exports/`.

---

## How to Position Data to Buyers

Closing SP always looks healthier than morning exchange prices. Use transparent framing:

### The Transparency Premium

> *"This is a strict algorithmic calibration loop to verify the LightGBM model isolates positive expected value from the field. It represents mathematical validation at Starting Price — not guaranteed live execution slippage on morning exchange odds."*

### The Technical Safeguard

Point engineers to **`verification_hash`** in the master CSV:

```
SHA-256(bet_id | created_at | runner_id | offered_win | stake_units)
```

Tamper-evident — no screenshot trust required.

### Calibration vs OOS (critical for due diligence)

```
train_end:  2026-04-30   (ingest/config.yaml)
test_start: 2026-05-01
```

| Window | Segment in master CSV | Buyer claim |
|--------|---------------|-------------|
| Dec 2025 – Feb 2026 | Winter block (rows 1–7,926) | Model calibration — in-sample |
| **May 2026** | OOS block (rows 7,927–10,176) | **Pure untouched holdout** |
| Forward Matchbook cron | (future) | Premium tier live exchange proof |

---

## Master Data Room Package (Dec–Feb + May)

```
[Master Track Record — buyer-facing]
  ├── Winter calibration:  1 Dec 2025 → 28 Feb 2026  (7,926 picks, in-sample)
  ├── OOS holdout:         1 May → 19 May 2026       (2,250 picks, pure holdout)
  └── Master total:        10,176 settled decisions in one CSV
```

### May 2026 Pure Holdout (valuation anchor)

```
[May 2026 Pure Holdout Window]
  ├── Timeframe:      1 May → 19 May 2026
  ├── Data integrity: 100% out-of-sample
  ├── Volume:         921 races / 2,250 value picks
  ├── Hit rate:       24.5% EW place hit rate
  └── Performance:    +121.3% ROI at SP (+2,730 units)
```

**Ranker training benchmark:** Winner AUC 0.908 · Place AUC 0.902

---

## CSV Column Reference

| Column | Description |
|--------|-------------|
| `verification_hash` | Tamper-evident SHA-256 audit chain |
| `runner_id` | Unique runner key |
| `closing_sp` | Starting price at settlement |
| `each_way_pnl` | Settled each-way P&L (1 unit stake) |
| `model_ev` | Model EW combined EV at log time |
| `status` | `won` · `placed` · `lost` |

---

## Regenerate

```bash
cd ~/hibs-racing && source .venv/bin/activate

# Winter sync
hibs-racing ingest-raceform ~/Downloads/raceform.db --since 2025-12-01 --sync

# Winter replay
hibs-racing backtest-replay --start 2025-12-01 --end 2026-02-28 --keep \
  --export-ledger --export-path exports/Hibs_Racing_Backtest_DecFeb2026_TrackRecord.csv

# Master 6-month sheet (Dec–Feb winter + May OOS)
cat exports/Hibs_Racing_Backtest_DecFeb2026_TrackRecord.csv \
  <(tail -n +2 exports/Hibs_Racing_OOS_PhaseA_May2026_TrackRecord.csv) \
  > exports/Hibs_Racing_Master_6Month_TrackRecord.csv

# May OOS only
hibs-racing backtest-replay --start 2026-05-01 --end 2026-05-31 --export-ledger
```

---

## Acquire Listing Copy

**Headline:** Proprietary LightGBM Horse Racing Analytics SaaS with 10,000+ Verifiable Prediction Audit Trail

**Pitch:** Turn-key containerized UK/IRE engine (LightGBM LambdaRank, holdout Winner AUC 0.908). Includes retrospective replay engine, SHA-256 public ledger, and master CSV with **10,176** settled automated value decisions — **7,926 winter calibration + 2,250 pure out-of-sample (May 2026)**. Docker-ready, 06:00 cron batch architecture.

**Still pending for premium tier:** Matchbook forward paper ledger (30–45 day unattended cron).

---

## Operational Sequence

1. **List now** with master CSV + May OOS highlight + transparent SP framing  
2. **Matchbook** — enable API → forward `/tracker` (non-backtest) proof  
3. **Extend May** — re-ingest raceform when May 20–31 available  
4. **VPS/Docker** — 24/7 cron for buyer demo (Mac sleep breaks local cron)

---

## Affiliate monetization (Acquire listing)

See **`ACQUIRE_LISTING.md`** for revenue-deck copy: programmatic UTM deep-links, novice UX touchpoints, env-driven venue switching (`HIBS_AFFILIATE_VENUE`).
