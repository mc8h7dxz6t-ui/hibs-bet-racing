# Technical Due Diligence FAQ — Hibs Racing Intelligence

Hand this to buyers who want a plain-English breakdown of the stack, proof methodology, and monetization layer.

---

## 1. What does the engine actually predict?

The core model is a **LightGBM LambdaRank** ranker trained on UK/IRE flat racing. For each race it scores every runner and produces a **relative ordering** (who is most likely to finish ahead of whom). Those scores feed downstream **place-probability** and **expected-value (EV)** gates used for value picks — not a single “win probability” headline number in isolation.

**Artifact paths:** `data/models/lgbm_ranker.txt`, `data/models/lgbm_ranker_features.json`

---

## 2. Why LambdaRank instead of plain classification?

Horse racing is inherently **listwise**: you care about ranking runners within a race, not independent yes/no labels. LambdaRank optimizes **NDCG-style** ranking loss — the model learns to push winners and place-getters toward the top of each race field. Relevance labels are derived from `finish_pos` per race (winner = highest relevance).

Training metrics reported in `train-ranker`: **NDCG@3**, **top-1 hit rate** on holdout races.

---

## 3. What features go into the model?

Features are built in `features/ranker_matrix.py` from the Raceform feature store (form, ratings, course/distance context, NLP-derived comment tags where available). The exact column list is frozen in `lgbm_ranker_features.json` at train time so inference is deterministic.

---

## 4. How is “out-of-sample” defined?

From `ingest/config.yaml`:

| Split | Date |
|-------|------|
| `train_end` | 2026-04-30 |
| `test_start` | 2026-05-01 |

### Institutional performance matrix (verified replays)

| Window | Label | ROI (SP) | Value picks | Top-1 win rate |
|--------|-------|----------|-------------|----------------|
| Nov 2025 – Apr 2026 | In-sample calibration | **+116.37%** | 16,541 | 81.3% |
| May 2026 (1–19) | Pure OOS holdout | **+124.14%** | 2,178 | 79.9% |

See **`ACQUIRE_LISTING.md`** for full B2B pitch table and honest in-sample framing.

The **May 2026 block** is **pure holdout** — no May rows were used in the last ranker training window. The **Nov–Apr block** overlaps `train_end` and demonstrates volume consistency at scale (document transparently as in-sample).

---

## 5. What is the verification hash?

Each settled pick row includes:

```
SHA-256(bet_id | created_at | runner_id | offered_win | stake_units)
```

Buyers can recompute hashes from the CSV without trusting screenshots. Public verifier UI: `/tracker?backtest=1`.

---

## 6. Why does ROI look high vs live exchange odds?

Backtest settlement uses **Starting Price (SP)**, which is the industry-standard calibration benchmark but **optimistic vs morning exchange prices** (slippage, market moves). The listing explicitly frames this as a **Transparency Premium** — mathematical validation, not guaranteed live execution P&L.

Forward proof on **Matchbook morning odds** requires API access + 30–45 days of cron (`scripts/daily_refresh.sh`).

---

## 7. How does affiliate monetization work?

| Layer | Role |
|-------|------|
| `utils/monetization.py` | Builds UTM-tagged partner URLs from runner/course/time |
| 06:00 batch | Attaches `monetized_link` to JSON pick payloads |
| Novice UX / Smart Portfolio | Clickable odds badges (`rel="noopener sponsored"`) |
| WhatsApp slip copy | Appends partner URL per selection |

**Venue switch:** set `HIBS_AFFILIATE_VENUE` (and optional `AFFILIATE_*_BASE_URL`) — no code deploy required.

Tests: `tests/test_monetization.py`, `tests/test_daily_webhook.py`.

---

## 8. Is live execution enabled for buyers?

**No — by design for this listing.** `EXECUTION_DISABLED = True` in `live/execution_config.py`. The asset ships as **analytics + paper ledger + affiliate UX**. Matchbook routing code exists but is gated; buyers enable when credentialed.

---

## 9. How do I run it locally?

```bash
cd hibs-racing
python -m venv .venv && source .venv/bin/activate
pip install -e ".[ranker,web]"
hibs-racing web --port 5003
# http://127.0.0.1:5003
```

Docker: see `DOCKER.md` — `docker compose up -d`.

---

## 10. What automated tests exist?

```bash
pytest tests/ -q
```

Key suites: monetization links, novice pick filtering, daily webhook digest, backtest replay, paper ledger settlement.

---

## 11. Data room deliverables

| Document | Purpose |
|----------|---------|
| `DATA_ROOM.md` | Audit trail positioning |
| `ACQUIRE_LISTING.md` | Acquire.com listing copy |
| `DATA_UPGRADE.md` | Paid API migration path |
| `docs/MATCHBOOK_API_REQUEST.md` | Exchange API onboarding template |
| `exports/Hibs_Racing_Master_6Month_TrackRecord.csv` | 10,176 settled picks (buyer file) |

**Repo:** `github.com/mc8h7dxz6t-ui/hibs-bet-racing`

---

## 12. Common buyer questions (quick answers)

**Q: Can I swap the exchange partner?**  
A: Yes — env var only (`HIBS_AFFILIATE_VENUE`).

**Q: Can I retrain on my own data?**  
A: Yes — `ingest-raceform` → `build-matrix` → `train-ranker`. Pipeline is CLI-driven.

**Q: What breaks if the Mac sleeps?**  
A: Local cron (`scripts/install_cron.sh`) — use Docker on a VPS for 24/7 ops.

**Q: Football asset included?**  
A: No — this repo is **Hibs Racing Intelligence** only. Football (`hibs-bet`) is a separate codebase/listing.
