# hibs-racing

**What this is:** Horse racing research — cards, paper ledger, backtest, evidence gates.  
**What this is not:** Enterprise fintech/cyber platform, SOC2-certified SaaS, or proven profitable betting product.

See [docs/FORENSIC_ARCHITECTURE_TRUTH.md](docs/FORENSIC_ARCHITECTURE_TRUTH.md) before any external diligence or sale conversation.

Separate offline racing engine under the hibs banner. **Does not import or modify hibs-bet football.**

## Phases

| Phase | Scope | Status |
|-------|--------|--------|
| **A** | comment ingest → **sectional NLP** (regex → optional spaCy) → feature store → place/top-3 backtest | Implemented |
| **B** | Harville place model + each-way EV + paper ledger + **card scoring** | Implemented (cards) |
| **C** | Betfair WOM stake scaler | Stub |

## Your two free accounts — recommended split

| Account | Role in hibs-racing | Command |
|---------|---------------------|---------|
| **Kaggle** (`raceform.db`) | Bulk history + **running comments** → NLP tags, combo priors, backtest | `hibs-racing ingest-raceform ~/Downloads/raceform.db --year 2026 --pipeline` |
| **The Racing API** (free plan) | **Today's/tomorrow's cards** — runners, OR, jockey/trainer (no comments) | `hibs-racing fetch-cards --source racing_api --day 1 --score` |

You do **not** need Racing Post login if the API + Kaggle cover your workflow. Keep rpscrape as a fallback for comments on recent days the DB hasn't caught up yet.

### 1. Kaggle → raceform.db (history + NLP)

1. On Kaggle, download the UK/Ireland **raceform.db** SQLite file (Horse Racing Results dataset).
2. Copy `.env.example` → `.env` and set `RACEFORM_DB_PATH` if you like.
3. One-time bulk load:

```bash
cd ~/hibs-racing && source .venv/bin/activate
pip install -e ".[dev]"

hibs-racing ingest-raceform ~/Downloads/raceform.db --year 2026 --pipeline
# tag + outcomes + ranker matrix; add --backtest for signal report
```

Re-run with `--since 2026-05-20` periodically if you download a fresher Kaggle dump.

### 2. The Racing API (live cards)

1. Sign in at [theracingapi.com](https://www.theracingapi.com) → **My Account** → copy **Username** and **Password**.
2. Add to `~/hibs-racing/.env`:

```env
RACING_API_USERNAME=your_username
RACING_API_PASSWORD=your_password
RACING_API_PLAN=free
```

3. Fetch and score:

```bash
hibs-racing fetch-cards --source racing_api --day 1 --region gb --score
hibs-racing fetch-cards --source racing_api --days 2 --region gb --score   # today + tomorrow
hibs-racing fetch-cards --source racing_api --day 1 --score --odds my_odds.csv --paper
```

Free plan hits `/v1/racecards/free` — basic fields only, **no running comments**. Scoring still works via your Kaggle-trained combo/NLP priors matched by horse name.

## Quick start (Mac)

```bash
cd ~/hibs-racing
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,api]"

hibs-racing ingest-raceform ~/Downloads/raceform.db --year 2026 --pipeline
hibs-racing fetch-cards --source racing_api --day 1 --score
```

## Upcoming cards + paper EW (Phase B)

| Source | Command | Notes |
|--------|---------|--------|
| **The Racing API** | `fetch-cards --source racing_api` | **Best if you have free API keys** — reliable cards |
| **Manual CSV** | `ingest-cards data/samples/cards_template.csv` | Always works |
| **rpscrape** | `fetch-cards --day 1` | Free scrape; needs RP cookies in `.env` if blocked |

```bash
hibs-racing build-matrix
hibs-racing train-ranker          # saves data/models/lgbm_ranker.txt
hibs-racing score-card --odds data/samples/odds_template.csv --paper
```

**Scoring:** when `data/models/lgbm_ranker.txt` exists, `score-card` uses the LightGBM LambdaRank model. Mac training needs `brew install libomp`. Set `ranker.scoring_mode: ranker` or `HIBS_RACING_PRODUCTION=1` on VPS to fail fast if artifacts are missing (no silent heuristic fallback).

Win probs → Harville place probs → EW EV vs offered prices.

### Retail odds (Oddschecker)

Scrape aggregated retail book prices (Bet365, William Hill, Ladbrokes, etc.) — best price per runner, exchanges excluded by default:

```bash
pip install -e ".[scraper]"
hibs-racing fetch-odds                              # → data/parquet/retail_odds.parquet
hibs-racing score-card --odds-source oddschecker    # scrape + EW value flags
```

Optional `race_urls.json` bypasses search when Oddschecker layout changes: `{"race_id": "https://www.oddschecker.com/horse-racing/..."}`.

Set `oddschecker.auto_scrape: true` in config to fall back to scraping when Racing API has no embedded prices.

### Matchbook exchange

REST API with username/password session token — best **back** price per runner (no certificate):

```bash
# .env: MATCHBOOK_USERNAME, MATCHBOOK_PASSWORD
pip install -e ".[api]"
hibs-racing fetch-odds --source matchbook
hibs-racing score-card --odds-source matchbook --paper
```

In `auto` mode: embedded Racing API prices → Matchbook (if creds set) → none.

### rpscrape fallback (optional)

If you also want RP comments for days after your Kaggle dump:

```env
EMAIL=your@email.com
ACCESS_TOKEN=cognito_access_token_from_racingpost_cookies
```

```bash
hibs-racing fetch-cards --day 1 --region gb --score
hibs-racing scrape --days 7 --ingest
```

## CSV schema

Required columns: `race_id`, `race_date`, `horse_id`, `finish_pos`, `comment`.  
Optional: `course`, `region`, `race_type`, `distance_f`, `going`, `field_size`, `sp_decimal`.

## Layout

```
hibs-racing/
  ingest/config.yaml      backfill date range + paths
  data/schema.sql         SQLite feature store
  src/hibs_racing/
    nlp/                  normalize + regex tagger
    features/             tag batch + next-run labels
    backtest/             place signal report
    place/                Phase B (Harville, EW EV, paper ledger)
    live/                 Phase C (Betfair WOM stub)
```

Run ingest on Mac or a tiny VPS — not on `/opt/hibs-bet`.

## Web UI (hibs-bet aligned)

Same Hibs crests, green/navy theme, and header pattern as **hibs-bet** — runs separately on **port 5003** (5001 is usually hibs-bet football).

```bash
cd ~/hibs-racing && source .venv/bin/activate
pip install -e ".[web]"

./start.sh web
# or explicit port
hibs-racing web --port 5003
# → http://127.0.0.1:5003
```

### Desktop launcher (macOS)

```bash
bash scripts/install_desktop_launcher.sh ~/Desktop
```

Installs **HIBS Racing.app** — starts the local dashboard and opens your browser (same pattern as hibs-bet football).

Pages: **Cards** (top places + monitor), **Tracker** (paper P&L + strike rates), **Backtest**, **Status**.

```bash
hibs-racing settle-paper          # match open bets to ingested results
hibs-racing score-card --odds my_odds.csv --paper
```

Future alignment: shared betslip/ledger styling, Betfair odds panel, cross-link from hibs-bet dashboard.
