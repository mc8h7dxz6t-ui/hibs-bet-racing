# Data upgrade guide — production feeds & schema mapping

This document is for buyers who outgrow free-tier APIs and need a clear path to paid, rate-limit-safe data without rewriting the analytics stack.

## Quick upgrade checklist

| Step | Action |
|------|--------|
| 1 | Choose a paid card/results vendor (see below) |
| 2 | Set env vars in `.env` (or Docker `environment:`) |
| 3 | Optionally bump `RACING_API_PLAN` or swap `--source` on `refresh-cards` |
| 4 | Run `hibs-racing refresh-cards --source racing_api` and verify `upcoming_runners` row counts |
| 5 | Re-run `hibs-racing settle-paper` after results ingest |

No code changes are required for **The Racing API** tier upgrades — only credentials and plan string.

---

## 1. Card & runner feeds → `upcoming_runners`

**Primary adapter:** `src/hibs_racing/ingest/racing_api.py`  
**Orchestration:** `src/hibs_racing/cards/refresh.py` (`refresh-cards` CLI)

### Environment variables

```bash
RACING_API_USERNAME=your_user
RACING_API_PASSWORD=your_password
RACING_API_BASE=https://api.theracingapi.com/v1
RACING_API_PLAN=free          # free | basic | standard
```

| Plan | Endpoint suffix | Notes |
|------|-----------------|-------|
| `free` | `/racecards/free` | Today/tomorrow only; rate limits apply |
| `basic` | `/racecards/basic` | More fields; higher quota |
| `standard` | `/racecards/standard` | Full card metadata |

The adapter reads `RACING_API_PLAN` and selects the endpoint from `ENDPOINTS` in `racing_api.py`. Upgrading is:

```bash
RACING_API_PLAN=standard
```

### JSON → SQLite column mapping

| Racing API field (runner/race) | `upcoming_runners` column |
|-------------------------------|----------------------------|
| `race_id` / synthetic key | `race_id` |
| `date` | `card_date` |
| `off_time` / `off_dt` | `off_time` |
| `course` | `course` |
| `region` | `region` |
| `race_name` | `race_name` |
| `type` | `race_type` |
| `race_class` / `class` | `race_class` |
| `going` | `going` |
| `field_size` | `field_size` |
| `distance_f` / `dist_f` | `distance_f` |
| `horse_id` / horse name | `horse_id` |
| `horse` / `horse_name` | `horse_name` |
| `draw` | `draw` |
| `ofr` / `or` | `official_rating` |
| `rpr` | `rpr` |
| `jockey` | `jockey` |
| `trainer` | `trainer` |
| `last_run` | `days_since_last_run` |
| `comment` / `spotlight` | `card_comment` |
| `odds_decimal` / `sp_dec` | `win_decimal` (fallback retail) |
| — | `runner_id` = `{race_id}_{horse_id}` |
| — | `source` = `racing_api` |
| — | `fetched_at` = UTC timestamp |

**Downstream:** `card_scores` is populated by `score_card.py` from `upcoming_runners` + ranker features. Value flags require exchange odds (Matchbook section below).

### Alternative vendors (Sportradar, Timeform, etc.)

The ingestion boundary is intentionally narrow:

1. Implement a parser that returns the same flat runner `DataFrame` as `parse_racing_api_payload()`.
2. Add a branch in `cards/refresh.py` for `--source your_vendor`.
3. Upsert into `upcoming_runners` using the existing store helpers.

Do **not** change ranker or paper-ledger code — only the card ingest adapter.

---

## 2. Historical results → `runners`

**Primary path:** Kaggle `raceform.db` via `hibs-racing ingest-raceform`  
**Sync:** `scripts/daily_refresh.sh` calls `--since {lookback}`

| Source column / concept | `runners` column |
|-------------------------|------------------|
| race id | `race_id` |
| horse id | `horse_id` |
| meeting date | `race_date` |
| finish position | `finish_pos` |
| SP | `sp_decimal` |
| in-running comment | `comment_raw` → NLP → `comment_tags` |

Paid upgrades: replace or supplement `raceform.db` with a commercial results API; map into the same CSV/SQLite ingest path in `ingest/csv_loader.py` and `ingest/raceform_sync.py`.

---

## 3. Exchange odds → value flags & steam gates

**Adapter:** Matchbook client under `src/hibs_racing/odds/matchbook.py` (invoked from `refresh-cards --odds-source auto`)

```bash
MATCHBOOK_USERNAME=
MATCHBOOK_PASSWORD=
MATCHBOOK_API_BASE=https://api.matchbook.com/edge/rest
```

| Matchbook concept | Stored / used in |
|-------------------|------------------|
| Win market price | `upcoming_runners.win_decimal`, `card_scores` EV |
| Place market price | `upcoming_runners.offered_place_decimal` |
| Pre-race drift | steam gate in dashboard + `notify-daily` digest |

Config toggles live in `ingest/config.yaml` → `matchbook:` block (poll intervals, drift thresholds).

**Betfair (optional):** credentials in `.env`; execution routing is disabled in analytics/sale mode — odds-only use remains available if enabled in config.

---

## 4. Scoring & features → `card_scores` / `ranker_features`

| Stage | Table | Producer |
|-------|-------|----------|
| Historical feature build | `ranker_features` | `hibs-racing build-features` / weekly retrain |
| Live card scoring | `card_scores` | `score_card.py` during `refresh-cards` |
| Model artifacts | `/data/models/lgbm_ranker.txt` | `hibs-racing train-ranker` |

Feature list is versioned in `data/models/lgbm_ranker_features.json` (tracked in git). Model weights stay in the data volume (not committed).

---

## 5. Paper ledger → `paper_bets` (public tracker)

When `refresh-cards --paper` runs (daily cron):

1. Value picks (`value_flag=1`, filters in `place/paper_ledger.py`) insert into `paper_bets`.
2. `settle-paper` resolves results from ingested `runners.finish_pos`.
3. `/tracker` exposes SHA-256 verification chain (`place/public_tracker.py`).

**Goal for due diligence:** 100+ settled rows with `status != 'open'` and consistent `verification_hash` chain.

---

## 6. Rate-limit & reliability patterns (already in codebase)

- **Sequential region fetch** with backoff in `racing_api.py` (429 handling).
- **`--workers 1`** in `daily_refresh.sh` for card refresh under free tier.
- **Batch-only analytics mode** — no live polling; morning snapshot only.

For scale, increase workers only after upgrading API tier:

```bash
hibs-racing refresh-cards --workers 4 --regions gb,ire
```

---

## 7. Recommended production `.env` template

```bash
RACING_API_PLAN=standard
RACING_API_USERNAME=...
RACING_API_PASSWORD=...
MATCHBOOK_USERNAME=...
MATCHBOOK_PASSWORD=...
HIBS_RACING_DATA_DIR=/data
HIBS_RACING_DB_PATH=/data/feature_store.sqlite
HIBS_PUBLIC_TRACKER=1
TELEGRAM_BOT_TOKEN=...          # optional productized output
TELEGRAM_CHAT_ID=...
```

---

## Support contacts (vendor docs)

- [The Racing API](https://www.theracingapi.com/documentation) — card/results tiers
- [Matchbook API](https://developers.matchbook.com/) — exchange odds
- [Sportradar Racing](https://developer.sportradar.com/) — enterprise feed (custom adapter)

Architecture principle: **swap adapters, keep schema**. The LightGBM ranker, paper ledger, and public tracker are feed-agnostic once rows land in `upcoming_runners` and `runners`.
