# AGENTS.md

## Cursor Cloud specific instructions

This repo is a **Python 3.12 monorepo** with two independent products that share one `pyproject.toml`:

1. **hibs-racing** — offline horse-racing NLP + place/EW research engine with a Flask web dashboard (default port **5003**). Package: `src/hibs_racing/`. Entry points: `hibs-racing` (CLI), `hibs-racing-web`.
2. **Institutional++ (inst++)** — 12 CLI-native audit/governance SKUs on a shared crypto-audit spine (`src/inst_spine/`), plus the `inst-workflow` FastAPI "Proof Console" UI (default port **8790**). Orchestrated via the `Makefile` + `scripts/demo_*.sh` / `scripts/instpp_*.sh`.

Everything is **SQLite-backed and offline-first** — no external DB/broker is required for tests or demos. Redis and PostgreSQL are optional production profiles only. All third-party APIs (The Racing API, Matchbook, OpenAI, SMTP) are optional and stubbed/skipped by default (`SKIP_LIVE=1`).

### Environment
- The update script creates/uses a virtualenv at `.venv` and installs `.[dev,instpp,web,api,ranker,scraper]` (covers both products). **Activate it first**: `source .venv/bin/activate`.
- Requires the `python3.12-venv` system package (installed during setup).
- `lightgbm` needs `libgomp` (already present on the base image).

### Running the apps
- **inst++ Proof Console UI:** `SKIP_LIVE=1 ./scripts/demo_gold_up.sh` → http://127.0.0.1:8790 (stop with `make demo-gold-down`). The script runs a `pip install` internally — harmless once deps are present.
- **inst++ full offline demo + verify:** `SKIP_INSTALL=1 ./scripts/demo_ready.sh` (preflight), then `SKIP_LIVE=1 make demo-all` and `make verify-portfolio` (writes `data/demo/portfolio/PORTFOLIO_MANIFEST.json` with `verified_ok: 12`).
- **racing web:** `HIBS_RACING_PRODUCTION=0 hibs-racing web` (port 5003). See README for CLI usage.

### Non-obvious caveats
- **`HIBS_RACING_PRODUCTION`:** `.env.example`/`.env` set this to `1`, which makes racing scoring **fail fast** (`RankerPreflightError`) if `data/models/lgbm_ranker.txt` is missing. For dev without a trained ranker, set `HIBS_RACING_PRODUCTION=0` to use the heuristic scorer.
- **Racing cards only appear in the web UI if `card_date` is within the next ~24h window.** To see data, ingest a card dated near-today, e.g. `hibs-racing init && HIBS_RACING_PRODUCTION=0 hibs-racing ingest-cards <cards.csv> --score --odds <odds.csv> --paper`. Sample templates live in `data/samples/`.
- **Product pills in the racing UI** (`⚽ Football`, `📈 Trading`, `📊 Lines` — the last is the FVE/Fair-Value-Engine "line trader") point to the separate **hibs-bet football / FVE** app, which is **not runnable in this repo**. `deploy/football-inst-overlay/` (`src/hibs_predictor/`) is only a *partial deploy overlay* — it is missing base modules (`app_logging`, `config`, `cache`, `auth`, `main`, …) and lives in a separate repository; importing `hibs_predictor.web` fails. In the user's deployment that app/FVE runs on its own host/port (e.g. `:7300`). By default Football → `/` and Trading/Lines → local paths that **404**; point them at the football host with `HIBS_FOOTBALL_BASE_URL` / `HIBS_TRADING_STATUS_URL` / `HIBS_LINE_TRADER_URL` (e.g. `http://127.0.0.1:7300`, `.../harvested-execution`, `.../line-trader`). The FVE upstream API/WS default base is `FVE_API_URL=http://127.0.0.1:8010`.
- **No linter is configured** (no ruff/flake8/black/mypy, no `lint` make target). Use `python -m compileall -q src` for a syntax check.

### Tests
- Full suite: `python -m pytest` (`testpaths = ["tests"]`). ~514 pass.
- **Known pre-existing failures on this branch (not environment issues):** `test_matchbook.py`, `test_odds_loader.py`, `test_smart_picks_nan.py`, `test_daily_webhook.py` fail because Matchbook is gated by the committed `.rate_limit_state.json` (`matchbook_gated`); `test_spend_guard.py::test_spend_guard_serve_mock_chat` passes in isolation but fails in a full run due to test-ordering SQLite state. These reproduce on a clean checkout.
