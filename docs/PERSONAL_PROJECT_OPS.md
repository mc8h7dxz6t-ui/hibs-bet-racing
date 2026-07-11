# Personal project operations — industry benchmarks, personal green lights

**This is a personal sports research stack.** Not for sale. Not enterprise SaaS. Not proof of profitable betting.

See also: [FORENSIC_ARCHITECTURE_TRUTH.md](FORENSIC_ARCHITECTURE_TRUTH.md), [compliance/claims-today-vs-blocked.md](compliance/claims-today-vs-blocked.md).

---

## What runs 24/7 (consolidated VPS)

| UTC | Job | Purpose |
|-----|-----|---------|
| */30 | `hands_off_cycle.sh` | Stack wiring, data producer repair, Inst++ watchdog |
| */15 | `cron-hibs-racing-watchdog.sh` | Restart racing if ping hung |
| 06:05 | `cron-hibs-racing-daily.sh` | Racing cards + paper settle |
| 06:35 | `cron-hibs-calibration.sh` | Football audit + pred-log-sync |
| 23:05 | Evening audit + sync | Settlement |
| */3h :20 | `warm_football_fixtures.sh` | Fixture cache (scrape-first) |
| 07:35, 14:35 | `seed_forward_evidence.sh` | Headless snapshots (matchdays) |

Install minimal crontab after bloat:

```bash
sudo bash /opt/hibs-bet/deploy/crontab-emergency-sports-only.sh
sudo bash /opt/hibs-bet/deploy/install-hibs-cron-sudoers.sh
```

---

## Cache preservation (low enrich ≠ destroy cache)

When `HIBS_PRESERVE_GREEN_CACHE=1` (default in overlay `.env`):

- Repair **does not bust** fixture cache if fixtures exist on disk.
- Health-light failure during gunicorn warm → **service restart only**.
- New bundle replaces old only when quality score improves by ≥2.0 (`HIBS_CACHE_REPLACE_MIN_DELTA`).

Module: `hibs_predictor/cache_preservation_policy.py`

---

## Personal staking green lights (when YOU may scale stakes)

```bash
bash /opt/hibs-bet/scripts/verify_personal_staking_greenlights.sh
```

| Lane | Green when | Industry reference (fact, not claim we meet it) |
|------|------------|--------------------------------------------------|
| **Football** | F1–F6 critical + F7–F9 + **F10 Brier** | Brier ≤0.22 on n≥30; CLV beat-close ≥50% on n≥25 |
| **Racing** | R1–R3 critical + R5–R8 | Place Brier ≤0.25 on n≥20; paper recon clean |
| **Trading** | Day-15 gate on VPS | Shadow soak → micro — `trading_core/` partial in repo |
| **FVE** | Lines export + remote worker | Operational only — not a staking lane |

`buyer_ready` / `evidence_gates_complete` = internal checklist. **Not** financial advice.

---

## Evidence gates (football F1–F10)

| Gate | Personal staking? |
|------|-------------------|
| F1–F6 | Infrastructure — must pass |
| F7–F9 | Forward CLV proof — must pass before stakes |
| F10 Brier | Calibration quality band |
| F9b/F9c | Informational only |

Summer: `matchdays_7d: 0` is **expected**. Do not force cache bust to “fix” gates.

---

## Racing observation lane

```bash
cd /opt/hibs-racing
bash scripts/install_observation_cron.sh   # daily 06:00 local, no weekly_retrain
```

`EXECUTION_DISABLED = True` — funded Matchbook API ≠ auto-stake.

---

## Brier / ROI — which number to trust

| Metric | Source | Use for staking? |
|--------|--------|------------------|
| Football 1X2 Brier | `prediction_log` monitor 28d | **Yes** (F10) |
| Racing place Brier | R8 gate / health | **Yes** |
| SP holdout ROI | `evidence_truth_plane` | **No** — calibration only |
| forward_offered ROI | paper ledger | **Yes** — live proof plane |
| Raw EV ROI | gate2 snapshots | **No** — proves gates work |

---

## Overlay sync (get latest audit fixes)

```bash
cd /opt/hibs-racing && git pull origin main
sudo OVERLAY_ROOT=/opt/hibs-racing/deploy/football-inst-overlay \
  bash /opt/hibs-racing/deploy/vps-sync-football-inst-overlay.sh
```

---

## Do not use for diligence

- `docs/*_SALES_*.md`, `ACQUIRE_LISTING.md`
- `buyer_ready` as PE pass
- Governor SKU names (IG/FG/MG/CG) — not in this repo

---

## Verify all lanes

```bash
curl -s http://127.0.0.1:8000/api/ping | python3 -m json.tool | head -5
bash /opt/hibs-bet/scripts/verify_football_evidence_gates.sh
bash /opt/hibs-bet/scripts/verify_personal_staking_greenlights.sh
bash /opt/hibs-racing/scripts/verify_racing_evidence_gates.sh
bash /opt/hibs-bet/scripts/institutional_failsafe_verify.sh
```
