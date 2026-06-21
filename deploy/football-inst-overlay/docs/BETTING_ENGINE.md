# hibs-bet betting engine — architecture & benchmark

How our stack compares to academic and industry football probability setups, what we do well, and the ranked improvement backlog.

## Current pipeline (summary)

1. **Fixture enrich** — API-Football / football-data.org fixtures, odds, form, standings, injuries, optional lineups (`data_aggregator.py`, scrapers).
2. **xG λ inputs** — priority chain: API xG → Understat light → league priors (`scraped_xg.py`, `HIBS_FBREF_BLOCKED` on VPS).
3. **Calibrated λ** — rank→Elo proxy + league home-advantage multipliers (`calibrated_lambdas.py`); motivation λ-nudge (`match_insight.py`).
4. **1X2 head** — Poisson score matrix (now **Dixon–Coles ρ** on low scores, default `HIBS_DIXON_COLES_RHO=-0.10`), optional RF+GB ensemble (`HIBS_1X2_MODE`), league profile + historic Brier shrink, mismatch dampening, H2H blend.
5. **Market blend** — de-vig 1X2 pulled toward book implied (`HIBS_CALIB_MARKET_BLEND`, scales up when data quality &lt; 75%).
6. **Side markets** — Poisson BTTS/O/U + empirical BTTS blend; joint score+BTTS from same λ.
7. **Value layer** — edge vs book + optional sharp consensus; Kelly; data-quality gates.
8. **Audit** — `prediction_log.py` snapshots, post-match join, Brier/CLV reports, `calibration_fit.py` → league shrink cache.

---

## A. How we compare (honest)

### Strengths vs top setups

| Area | hibs-bet | Best-in-class |
|------|----------|---------------|
| **Transparency** | Full payload: λ, shrink source, blend weights, rejection reasons | Often black-box API |
| **Data honesty** | Abstains on thin coverage; no dummy probs in prod | Many apps always show a number |
| **xG + context** | Real xG chain, injuries→λ, motivation, lineup confidence | Top shops similar; we match mid-tier pro |
| **Market respect** | De-vig blend + sharp consensus path + cross-book steam filter | Standard for serious CLV-focused desks |
| **Calibration loop** | SQLite audit → league Brier → shrink; fit script to cache | Mature ops run weekly isotonic/Platt + CLV dashboards |
| **Value discipline** | Multi-layer gates (DQ, confidence, longshot caps, table/xG disagree) | Comparable to conservative syndicate rules |

### Weaknesses vs best-in-class

| Gap | Impact |
|-----|--------|
| **No full Dixon–Coles time-decay fit** | ρ is fixed env default with **match-style restriction** on extreme λ profiles; per-league grid-fit from `calibration_fit` bypasses restriction |
| **ML ensemble untrained in prod** | RF/GB default to Poisson fallback unless `train()` run on historic matrix |
| **No standalone Elo time series** | Rank proxy only when standings exist; no cross-season team rating |
| **Independent Poisson for BTTS/O/U** | Industry often uses copula or bivariate Poisson for joint tails |
| **No live in-play model** | Pre-match only; live poll is display |
| **Calibration sample size** | League shrink needs ~25+ scored rows; new leagues stay at shrink=1.0 |
| **CLV off by default** | `HIBS_CLV_LOG_ENABLED=0` on most deploys until ops enables |

**Bottom line:** We sit **above typical consumer tipsters** (real xG, market blend, audit trail, strict value gates) and **below dedicated quant books** (fitted DC+MLE, trained ensembles, continuous CLV-driven recalibration, in-play).

---

## B. Ranked improvements

### Implementable in this codebase (priority)

1. **Enable CLV + cron `pred-log-sync`** — ops; code ready (`prediction_log.py`). *Impact: high for measuring edge.*
2. **Run `calibration_fit` weekly on VPS** — writes `.cache/calibration_v1.json`; engine already reads it. *Impact: medium-high.*
3. **Train ML head on audit export** — `BettingEngine.train()` + export from `prediction_log`; set `HIBS_1X2_MODE=blend_all`. *Impact: medium.*
4. **League-specific ρ** — fit `HIBS_DIXON_COLES_RHO` per league from scored low-score frequency in audit DB. *Impact: medium (draw calibration).*
5. **Bivariate Poisson / copula for BTTS** — extend side-market λ joint. *Impact: medium.*
6. **Dynamic blend from CLV** — raise `HIBS_CALIB_MARKET_BLEND` when league CLV beat-close &lt; 50%. *Impact: medium.*
7. **Isotonic 1X2 calibrator** — sklearn on audit probabilities per league bucket. *Impact: medium.*
8. **Elo time series module** — update ratings from results log, feed λ prior. *Impact: medium-long.*

### Research / external backlog

- Full Dixon–Coles + bivariate Poisson MLE (Maher 1982, Dixon & Coles 1997).
- Player-level xG models (StatsBomb open data style).
- In-play Bayesian updating.
- Exchange / Pinnacle-only anchor as primary implied (licensing/API).
- Monte Carlo tournament sims for cup motivation.

---

## C. Recent quick wins (this pass)

1. **Dixon–Coles ρ** — `HIBS_DIXON_COLES_RHO` (default `-0.10`, `0` disables) on 1X2 Poisson matrix in `betting_engine.py`.
2. **DQ-aware market blend** — when data quality &lt; 75%, blend weight increases up to 18% cap (trust market more on thin data).

Existing (already in tree):

- Historic Brier shrink via `league_shrink_for_predict` + `calibration_fit`.
- `HIBS_CALIB_MARKET_BLEND` base 8% toward de-vig implied.
- Motivation λ-nudge, injury λ adjust, sharp consensus value path.

---

## Environment reference

| Variable | Default | Role |
|----------|---------|------|
| `HIBS_1X2_MODE` | `ensemble` | `calibrated_poisson`, `blend_all`, `ensemble` |
| `HIBS_DIXON_COLES_RHO` | `-0.10` | Low-score correlation; `0` = independent Poisson |
| `HIBS_DIXON_COLES_RHO_MATCH_STYLE` | `1` | Scale fixed ρ toward 0 on extreme λ mismatch/totals until per-league MLE |
| `HIBS_CALIB_MARKET_BLEND` | `0.08` | 1X2 blend toward de-vig book implied |
| `HIBS_PREDICTION_LOG_ENABLED` | `0` | Audit snapshots (VPS safe profile sets `1`) |
| `HIBS_CLV_LOG_ENABLED` | `0` | Opening/closing odds for CLV |
| `HIBS_CALIB_FIT_DAYS` | `90` | Window label for calibration-fit (audit rows) |
| `HIBS_CALIB_FIT_MIN_ROWS` | `20` | Min scored rows per league before shrink is written |
| `HIBS_USE_INJURY_LAMBDA_ADJUST` | off | Attack availability → λ cut |
| `HIBS_ACCA_RECOMMENDER` | `1` | Insights/API stat acca suggestions (`0` disables) |
| `HIBS_ACCA_MAX_LEGS` | `5` | Max legs for “Acca of the day” on `/insights` |

See also `docs/ROADMAP.md` and `/insights` on the live dashboard.

---

## D. VPS ops — CLV + weekly calibration

### Enable (one-time)

Safer 2GB profile sets audit + CLV automatically:

```bash
sudo bash /opt/hibs-bet/deploy/apply-vps-safe-production.sh
```

Or manually in `.env`:

```bash
HIBS_PREDICTION_LOG_ENABLED=1
HIBS_CLV_LOG_ENABLED=1
```

Restart gunicorn after `.env` changes: `sudo systemctl restart hibs-bet`.

### Cron (recommended)

Print or install cron lines:

```bash
sudo bash /opt/hibs-bet/deploy/cron-hibs-calibration.sh --print
sudo bash /opt/hibs-bet/deploy/cron-hibs-calibration.sh --install
```

Manual one-liners (www-data crontab):

```cron
30 6 * * * cd /opt/hibs-bet && HOME=/opt/hibs-bet PYTHONPATH=src /opt/hibs-bet/.venv/bin/python -m hibs_predictor.main pred-log-sync >> /var/log/hibs-bet/pred-log-sync.log 2>&1
0 7 * * 0 cd /opt/hibs-bet && HOME=/opt/hibs-bet PYTHONPATH=src /opt/hibs-bet/.venv/bin/python -m hibs_predictor.main calibration-fit >> /var/log/hibs-bet/calibration-fit.log 2>&1
```

**Daily `pred-log-sync`**: joins FT scores, post-match xG, and (when `HIBS_CLV_LOG_ENABLED=1`) closing 1X2 from API-Football fixture odds.

**Weekly `calibration-fit`**: reads scored audit rows → writes `.cache/calibration_v1.json`; `betting_engine.py` applies league shrink on next prediction.

### Verify

| Check | Command / URL |
|-------|----------------|
| Sync ran | `tail /var/log/hibs-bet/pred-log-sync.log` — expect `Updated snapshot row(s): N` |
| Brier + CLV JSON | `cd /opt/hibs-bet && PYTHONPATH=src .venv/bin/python -m hibs_predictor.main pred-log-report` — includes `clv_by_league` |
| Calibration cache | `cat .cache/calibration_v1.json` — `leagues` map with `shrink`, `brier`, `n` |
| Dashboard status | `/status` → **Audit & calibration** section (beat-close % by league when data exists) |
| Token API | `GET /api/audit/summary?token=$HIBS_AUDIT_API_TOKEN` — full audit payload |
| Health | `GET /api/health` — `audit_ops.clv_by_league`, `audit_ops.calibration_cache` |

CLV requires snapshots taken **before** kickoff with a `best_bet` outcome; closing odds are joined only after FT via `pred-log-sync`.
