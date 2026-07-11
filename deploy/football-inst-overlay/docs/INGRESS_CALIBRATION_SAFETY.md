# Ingress, Calibration & Safety Architecture

Industry-standard data plane for sharp odds ingress, calibration circuit breakers, and execution guards.

## Odds ingress (football)

| Layer | Component | Role |
|-------|-----------|------|
| Sharp feed | `OddsPapiClient` | Pinnacle, Singbet, Betfair Exchange via oddspapi.io |
| Fail-closed | `schema_guard.py` | Semver contract + structural null rejection |
| Mapping | `price_truth_ingress.py` | `all_bookmaker_odds` + `price_truth` seed |
| Baseline | `football_data_csv_baseline.py` | Football-Data.co.uk closing-line matrices |

### Enable sharp ingress (deprecate retail Odds API)

```bash
export HIBS_DEPRECATE_ODDS_API=1
export ODDSPAPI_API_KEY=...
# optional: HIBS_ODDS_INGRESS=oddspapi
```

`DataAggregator._fetch_odds_bundle` prefers OddsPapi when enabled; retail `OddsApiClient` is skipped.

### CSV baseline (offline / research)

```bash
export HIBS_FOOTBALL_DATA_CSV_DIR=/path/to/football-data.co.uk
python -c "
from pathlib import Path
from hibs_predictor.ingress.football_data_csv_baseline import load_baseline_matrix
print(len(load_baseline_matrix(Path('$HIBS_FOOTBALL_DATA_CSV_DIR'), limit=10)))
"
```

## Brier runtime circuit breaker

FSM: `CLOSED` → `OPEN` (lockout) → `HALF_OPEN` (probe) → `CLOSED`.

| Domain | Threshold | Min n | Env |
|--------|-----------|-------|-----|
| Football F10 | 0.22 | 30 | `HIBS_F10_BRIER_THRESHOLD` |
| Racing R8 place | 0.25 | 20 | `HIBS_BRIER_LOCKOUT_THRESHOLD` |

Hourly cron:

```bash
sudo bash /opt/hibs-bet/scripts/run_brier_circuit_breaker.sh
```

On trip: sets `HIBS_EXECUTION_LOCKOUT=1`, persists `data/brier_circuit_state.json`, appends hash-chain ledger entry.

Staking gates (`personal_staking_gates.py`) and racing `ExecutionRouter` honour `execution_lockout_active()`.

## Redis multi-pod steam guard

- Script: `redis_scripts/market_steam.lua`
- Client: `hibs_racing.redis_guardrail_client.RedisGuardrailClient`
- Wired in `market_steam.detect_steam_drift` (Matchbook poll path)

```bash
export HIBS_REDIS_URL=redis://127.0.0.1:6379/0
```

Falls back to in-process dict when Redis unavailable (single-pod dev).

## WAL + execution slippage

| Stream | WAL hook | Path |
|--------|----------|------|
| Matchbook REST | `capture_before_parse` in `MatchbookClient._get` | `matchbook/` |
| rpscrape CSV | `normalize_rpscrape_csv` | `rpscrape/` |

`.wrcap` format: magic + seq + raw bytes (mmap-readable).

Slippage guard (`hibs_racing.execution.slippage_guard`):

- EV burn > 1.5% → `HELD` (no capital at risk)
- `serializable_order_guard` for PostgreSQL `SERIALIZABLE` order rows
- Wired in `MatchbookExecutionAdapter` when `model_win_prob` present on intent

## VPS sync

After merge, run both overlay sync steps on the VPS (see `VPS_FAILURE_MODES.md`).
