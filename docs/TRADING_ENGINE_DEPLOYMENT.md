# Trading Engine + Liquidity Router — VPS Deployment Runbook

Phased rollout for the event-driven trading sandbox on hibs-bet.co.uk. Default posture: **simulation only** — `HIBS_LIVE_TRADING_ENABLED=false` and `HIBS_LIQUIDITY_ROUTER_ACTIVE=false`.

> **VPS path:** racing code and `.env` live at `/opt/hibs-racing` (GitHub repo name is `hibs-bet-racing`). SQLite feature store: `/opt/hibs-racing/data/feature_store.sqlite`.

---

## Phase 1 — Sync code

```bash
sudo HIBS_RACING_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-racing-from-github.sh
```

Schema (`simulated_trades`, `routing_decisions`, `hedged_ledger_events`) is applied automatically on first daemon start via `init_db()` / `ensure_trading_schema()`.

---

## Phase 2 — Environment (sandbox defaults)

Edit `/opt/hibs-racing/.env` or use the idempotent helper:

```bash
sudo bash /opt/hibs-racing/deploy/apply-trading-daemon.sh
```

Required keys (all safe defaults):

```env
HIBS_LIVE_TRADING_ENABLED=false
HIBS_LIQUIDITY_ROUTER_ACTIVE=false
HIBS_EXECUTION_LATENCY_MAX_MS=250
HIBS_SLIPPAGE_MAX_TICKS=2
# HIBS_MATCHBOOK_STREAM_WS_URL=   # unset — Matchbook REST-only; inject-only idle mode
# HIBS_MIN_HEDGE_DELTA_BPS=150
# HIBS_MAX_VENUE_COMMISSION_BPS=200
# HIBS_LIQUIDITY_ROUTER_POLL_SEC=5
```

---

## Phase 3 — Install systemd daemon (soak)

```bash
sudo bash /opt/hibs-racing/deploy/apply-trading-daemon.sh --enable
```

Verify:

```bash
/opt/hibs-racing/.venv/bin/hibs-racing trading-status
systemctl status hibs-trading-daemon --no-pager
```

Inject a test order (no live capital):

```bash
/opt/hibs-racing/.venv/bin/hibs-racing trading-dispatch \
  --market-id 100 --runner-id 200 --odds 5.0 --stake 10 \
  --inject-odds 100:200:5.0
```

Expect `status: SIMULATED` in output and a row in `simulated_trades`. With line movement injected, `recent_hedged_events` may populate when delta exceeds `HIBS_MIN_HEDGE_DELTA_BPS`.

---

## Phase 4 — Soak checklist (before arming flags)

| Check | Command / signal |
|-------|------------------|
| Daemon running | `systemctl is-active hibs-trading-daemon` |
| Wallet seeded | `trading-status` → `wallet_id: default` |
| Simulated trades | dispatch smoke test above |
| Router ledger | `recent_hedged_events` in `trading-status` after steam inject |
| No outbound | `HIBS_LIQUIDITY_ROUTER_ACTIVE=false` → `outbound_blocked=1` on routes |

---

## Phase 5 — Arming (not yet supported in production)

Do **not** set `HIBS_LIVE_TRADING_ENABLED=true` or `HIBS_LIQUIDITY_ROUTER_ACTIVE=true` until outbound broker paths are explicitly certified. Both flags remain fail-closed in this build.

---

## CLI reference

| Command | Purpose |
|---------|---------|
| `hibs-racing trading-daemon` | Background stream + governor + liquidity router loop |
| `hibs-racing trading-dispatch` | One-shot order through execution governor |
| `hibs-racing trading-status` | Wallet, stream stats, recent trades + hedged events |
