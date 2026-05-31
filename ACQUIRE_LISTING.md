# Acquire.com Listing — Hibs Racing Intelligence

**Headline:** Proprietary LightGBM Horse Racing Analytics SaaS with 10,000+ Verifiable Prediction Audit Trail

---

## Programmatic Affiliate Monetization Engine

The codebase includes an isolated utility layer (`monetization.py`) that instantly transforms raw predictive data into trackable retail conversions.

**Dynamic Deep-Linking:** The **06:00 AM** batch script (`scripts/daily_refresh.sh`) processes daily selections and attaches strict UTM-tagged partner links directly to the JSON payload (`monetized_link` on pick candidates and morning digest rows). Telegram/Discord webhooks (`notify-daily`) carry the same links in the premium daily sheet.

**High-Conversion UI/UX Touchpoints:** Frontend components (Novice UX cards and one-click WhatsApp bet slip copies) seamlessly display clickable odds badges targeting the chosen exchange provider (`static/racing_ui.js`, `/api/monitor` hero cards).

Example slip output:

```
Hibs Smart Pick: 14:30 Epsom - Golden Fleece (4.5 EW) - Each-Way
Secure these odds via our verified partner: https://www.matchbook.com?utm_source=hibs_racing_app&...
```

**Zero-Downtime Infrastructure Refactoring:** Switching the entire platform's affiliate traffic from Matchbook to alternative networks (e.g., Betfair, Entain) requires **no codebase modifications** — it is entirely driven by updating environment variables (`HIBS_AFFILIATE_VENUE`) inside the root configuration block:

```bash
HIBS_AFFILIATE_VENUE=matchbook          # matchbook | betfair | oddschecker (+ custom AFFILIATE_*_BASE_URL)
AFFILIATE_MATCHBOOK_BASE_URL=https://www.matchbook.com/
```

---

## Core Asset Summary

| Layer | Detail |
|-------|--------|
| Engine | LightGBM LambdaRank · holdout Winner AUC **0.908** |
| Proof ledger | **10,176** settled backtest picks · SHA-256 `verification_hash` |
| OOS holdout | **2,250** May 2026 picks (post `train_end`) |
| Winter calibration | **7,926** Dec–Feb 2026 picks |
| Operations | 06:00 cron batch · Docker `docker compose up -d` |
| Data room | `DATA_ROOM.md` · `exports/Hibs_Racing_Master_6Month_TrackRecord.csv` |

---

## Buyer Framing (Transparency Premium)

> *Strict algorithmic calibration loop — mathematical validation at Starting Price, not guaranteed live execution slippage. May 2026 block is pure out-of-sample holdout; winter block demonstrates distribution fit across thousands of runners.*

Forward Matchbook paper ledger (30–45 day cron) layers on top once API access is enabled.

---

## Technical Due Diligence Pack

- `DATA_ROOM.md` — audit trail positioning
- `DATA_UPGRADE.md` — paid API migration path
- `DOCKER.md` — single-command deploy
- `docs/MATCHBOOK_API_REQUEST.md` — exchange API onboarding template
- GitHub: `mc8h7dxz6t-ui/hibs-bet-racing`
