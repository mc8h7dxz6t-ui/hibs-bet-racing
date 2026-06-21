# Metrics upgrade ladder

Institutional metric improvements without lowering data-quality floors. Three layers — apply in order.

## Layer 1 — Enrich / DQ (never lower floors)

| Metric | Module | Action |
|--------|--------|--------|
| CLV fair close | `clv_institutional.py` + `price_truth.enrich_clv_price_truth` | Margin-lift fair closing odds, `edge_clv_pct`, `mu_clv_log` |
| Odds capture | `prediction_log.audit_odds_capture_stats` | Fix capture gaps; do not relax completeness thresholds |
| Book panel | `price_truth.attach_price_panel_to_prediction` | Persist multi-book snapshots at prediction time |
| Racing DQ | `cards/data_quality.py` | Field completeness gates unchanged |

**Rule:** During a forward evidence window, only capture fixes and scheduled `calibration-fit` — no gate threshold changes.

## Layer 2 — Calibration (improves Brier)

| Metric | Module | Action |
|--------|--------|--------|
| League shrink | `historic_calibration` + cache file | Run `calibration-fit` after sufficient settled rows |
| Drift monitor | `calibration_drift.drift_summary_dict` | Alert on rolling Brier vs baseline |
| FVE model vs market | `football-app/backtest.py` | `evaluate_vs_market` on paired fixtures |
| Racing reliability | `hibs_racing.analytics.reliability_bins` | Win-prob bins from settled paper ledger |

## Layer 3 — Selection / gates (improves CLV beat-close)

| Metric | Module | Action |
|--------|--------|--------|
| Gate profiles | `gate_profile_compare` + `scripts/compare_gate_profiles.py` | Offline A/B on settled audit rows |
| CLV by league | `prediction_log.clv_beat_close_by_league` | League-specific beat-close rates |
| Trading spread | `spread_slippage_audit` + `scripts/suggest_assumed_spread_bps.py` | Align `assumed_spread_bps` with live p95 |

## Audit script

```bash
bash scripts/metrics_upgrade_audit.sh
```

Runs institutional-check, gate compare summary, calibration cache probe, and trading spread suggestion (when audit JSONL exists).

## Evidence gates (unchanged floors)

Football F7–F9, racing R5–R7, trading promotion scorecard thresholds remain as documented in `docs/NINE_TEN_SCORECARD.md`. Metric upgrades improve headline numbers; gates still require calendar-bound forward evidence.
