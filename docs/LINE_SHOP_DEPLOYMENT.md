# Line Shop (FVE Matrix) — Football VPS Deployment

The Line Shop UI ships in the hibs-bet-racing overlay (`deploy/football-inst-overlay/`). `/opt/hibs-bet` is **not** a git repo on VPS — copy overlay files after syncing racing.

---

## Phase 1 — Sync racing (overlay source)

```bash
sudo HIBS_RACING_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-racing-from-github.sh
```

---

## Phase 2 — Copy overlay + upsert football `.env`

```bash
sudo bash /opt/hibs-racing/deploy/apply-line-shop-football.sh
```

This script:

- Copies `line_trader.html`, `line_trader_shop.js`, `fve_ws_lines.js`, `fve_status.py`, `web.py` into `/opt/hibs-bet`
- Upserts FVE / Line Shop keys in `/opt/hibs-bet/.env`
- Restarts `hibs-bet`

Default env block appended:

```env
HIBS_FVE_INTEGRATION=1
HIBS_LINE_TRADER_URL=/line-trader
HIBS_FVE_DECAY_TIMEOUT_SECS=120
HIBS_FVE_ARB_DELTA_BPS=50
HIBS_FVE_STATUS_TTL_SEC=12
HIBS_FVE_FORCE_PAUSED=0
FVE_API_URL=http://127.0.0.1:8010
HIBS_FVE_PUBLIC_API_URL=https://hibs-bet.co.uk/fve-api
HIBS_FVE_PUBLIC_WS_URL=wss://hibs-bet.co.uk/fve-api
```

---

## Phase 3 — Verify

```bash
curl -sS -o /dev/null -w 'ping=%{http_code}\n' http://127.0.0.1:8000/api/ping
curl -sS -o /dev/null -w 'line-trader=%{http_code}\n' http://127.0.0.1:8000/line-trader
```

Open `https://hibs-bet.co.uk/line-trader` in a browser — FVE matrix, decay timer, and value highlights should render (presentation only; no live execution).

---

## Rollback

Remove `/opt/hibs-bet/templates/line_trader.html` and restart `hibs-bet`. Set `HIBS_FVE_INTEGRATION=0` in `/opt/hibs-bet/.env` to hide nav links without deleting files.
