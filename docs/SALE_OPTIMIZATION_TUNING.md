# Sale Optimization Tuning (Local Testing)

Apply these **locally first**. Do **not** deploy to VPS until `final-data-room-backtest.log` completes on the current elite backfill.

## Racing (`hibs-racing`)

Configured in `ingest/config.yaml` → `paper`:

| Parameter | Default (optimized) | Effect |
|-----------|---------------------|--------|
| `min_place_ev` | **0.12** (was 0.05) | Cuts marginal EW picks (~30% volume drop) |
| `min_combo_bayes_place` | **0.28** (was 0.22) | Requires stronger jockey–trainer prior |
| `harville_longshot_win_prob_threshold` | **0.03** | Implied win % below 3% |
| `harville_longshot_discount` | **0.85** | Scales longshot Harville input |

### Re-measure OOS ROI

```bash
cd ~/hibs-racing && source .venv/bin/activate
hibs-racing backtest-replay --start 2026-05-01 --end 2026-05-19 --keep --export-ledger
```

Compare pick count and ROI vs baseline +121.3% May holdout.

## Football (`hibs-bet`)

Enable via env (VPS `.env` **after** current pipeline finishes):

```bash
HIBS_SALE_OPTIMIZATION=1
# or individually:
HIBS_1X2_LAPLACE_ALPHA=0.85
HIBS_PREDICT_MIN_DATA_QUALITY_PCT=75
```

| Tweak | Mechanism |
|-------|-----------|
| Laplace smoothing | `f = 0.85·f_raw + 0.15·(1/3)` on 1X2 before audit commit |
| DQ abstain | `data_quality < 75%` → `abstained_low_dq` (no forced guess) |

Config mirror: `config/league_profiles.yaml` → `sale_optimization` (`enabled: false` until deploy).

### Re-measure Brier

```bash
cd ~/Applications && source .venv/bin/activate
HIBS_SALE_OPTIMIZATION=1 PYTHONPATH=src python -m hibs_predictor.main pred-log-backtest --days 120
```
