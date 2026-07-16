# McFadden Win Engine — Production Deployment Runbook

Industry-standard phased rollout for the sandboxed conditional logit win engine on hibs-bet.co.uk. Default posture: **engine scores in background; frontend release blocked** until calibration passes.

---

## Phase 1 — Deploy code (VPS)

Sync racing first, then football UI:

```bash
sudo HIBS_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-racing-from-github.sh
sudo HIBS_SYNC_REF=main bash /opt/hibs-bet/deploy/vps-sync-from-github.sh
```

Or use the repo helper after merge:

```bash
sudo bash /opt/hibs-bet-racing/deploy/apply-win-engine-env.sh   # idempotent env upsert
sudo systemctl restart hibs-racing
sudo systemctl restart hibs-bet   # or gunicorn equivalent
```

---

## Phase 2 — Production environment config

Edit the live racing `.env` on the VPS:

```bash
sudo nano /opt/hibs-bet-racing/.env
```

Append or verify **exactly** these flags at the bottom (leave active **false** until Phase 4):

```env
# McFadden Win Engine Staging Configuration (Leave as false initially)
HIBS_WIN_ENGINE_ACTIVE=false
HIBS_RACING_WIN_BRIER_PASS_MAX=0.185
HIBS_RACING_MIN_WIN_CALIBRATION_N=100
```

Optional tuning (defaults are safe):

```env
HIBS_WIN_ENGINE_ALPHA=1.0
HIBS_WIN_ENGINE_BETA=0.35
```

Save (`Ctrl+O`, Enter) and exit (`Ctrl+X`), then reload:

```bash
sudo systemctl restart hibs-racing
```

**Idempotent alternative** (no manual nano):

```bash
sudo bash /opt/hibs-bet-racing/deploy/apply-win-engine-env.sh
sudo systemctl restart hibs-racing
```

---

## Phase 3 — Post-deployment verification audits

Run the bundled probe (local or from Mac against production):

```bash
# On VPS (full DB + HTTP checks)
sudo bash /opt/hibs-bet-racing/scripts/verify_win_engine_deploy.sh

# From dev machine (HTTP only; set DB path if SSH'd)
HIBS_PRODUCTION_URL=https://hibs-bet.co.uk \
  HIBS_RACING_DB_PATH=/opt/hibs-bet-racing/data/feature_store.sqlite \
  bash /opt/hibs-bet-racing/scripts/verify_win_engine_deploy.sh
```

### Manual audit equivalents

#### 1. Extended parsing engine (combinations API)

```bash
curl -sS "https://hibs-bet.co.uk/api/racing/tips/combinations?date=2026-05-31" | python3 -m json.tool
```

**Expected:** JSON with `ok`, `combinations`, and `singles` keys. No `win_engine` block while `HIBS_WIN_ENGINE_ACTIVE=false`.

#### 2. Sandboxed win engine API cloak

```bash
curl -i -s "https://hibs-bet.co.uk/api/racing/win-engine/predictions" | head -20
```

**Expected:** `HTTP/1.1 404` and body `{"error":"win_engine_inactive",...}` — confirms public proxy does **not** expose model output while inactive.

> **Note:** Do not use `curl https://hibs-bet.co.uk` for this check; the football dashboard returns `200` HTML by design.

#### 3. Database schema migration integrity

```bash
sqlite3 /opt/hibs-bet-racing/data/feature_store.sqlite \
  "PRAGMA table_info(win_engine_predictions);"
```

**Expected:** columns include `runner_id`, `race_id`, `true_probability`, `fair_odds`, `brier_score`, `timestamp`.

```bash
sqlite3 /opt/hibs-bet-racing/data/feature_store.sqlite \
  "SELECT calibration_state, rolling_brier, sample_n FROM win_engine_calibration WHERE id=1;"
```

**Expected:** `UNCALIBRATED` initially (until enough settled races).

#### 4. Structural UI health probe (football dashboard)

```bash
curl -sS "https://hibs-bet.co.uk/" | grep -o 'id="system-bets-mount"' | head -1
curl -sS "https://hibs-bet.co.uk/" | grep -o 'hibs_system_bets.js' | head -1
```

**Expected:** both patterns present — sidebar mount + deferred fetch script. Dual-insight columns appear only when `win_engine.insights` is present in the combinations payload (Phase 4).

---

## Phase 4 — Flipping the live switch (when ready)

1. Let `refresh-cards` / cron run `run_win_engine_sandbox()` silently for at least one card cycle (24h recommended).
2. Check calibration ledger:

```bash
sqlite3 /opt/hibs-bet-racing/data/feature_store.sqlite \
  "SELECT * FROM win_engine_calibration;"
```

3. **Go-live criteria:**
   - `calibration_state = CALIBRATED`
   - `rolling_brier` ≤ `0.185` (or your `HIBS_RACING_WIN_BRIER_PASS_MAX`)
   - `sample_n` ≥ `HIBS_RACING_MIN_WIN_CALIBRATION_N`

4. Enable release:

```bash
sudo sed -i 's/^HIBS_WIN_ENGINE_ACTIVE=.*/HIBS_WIN_ENGINE_ACTIVE=true/' /opt/hibs-bet-racing/.env
# or: sudo bash /opt/hibs-bet-racing/deploy/apply-win-engine-env.sh --active
sudo systemctl restart hibs-racing
```

5. Re-run verification:

```bash
curl -sS "https://hibs-bet.co.uk/api/racing/tips/combinations" | python3 -c \
  "import sys,json; d=json.load(sys.stdin); print('win_engine' in d, d.get('win_engine',{}).get('calibrated'))"
```

**Expected:** `True True` when tips exist and engine is calibrated.

The dashboard sidebar will then show **WIN VALUE** (live vs fair) and **PLACE VALUE** (R8 place %) on leg cards without page reload.

---

## Rollback

```bash
sudo sed -i 's/^HIBS_WIN_ENGINE_ACTIVE=.*/HIBS_WIN_ENGINE_ACTIVE=false/' /opt/hibs-bet-racing/.env
sudo systemctl restart hibs-racing
```

Background scoring continues; frontend release is immediately suppressed.

---

## Related

| Artifact | Path |
|----------|------|
| Model service | `src/hibs_racing/models/win_engine_service.py` |
| Circuit breaker | `src/hibs_racing/models/win_engine_circuit.py` |
| Migration | `migrations/005_win_engine_predictions.sql` |
| Env template | `.env.example` |
| Verify script | `scripts/verify_win_engine_deploy.sh` |
