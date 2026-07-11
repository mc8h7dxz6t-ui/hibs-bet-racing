# Ordered recovery runbook — hands-off automation for all platforms

**Host:** `hibs-bet.co.uk`  
**Stacks:** Football `:8000` · Racing `:5003` · FVE `:8010` (or remote `.75`) · Trading metrics `:9108` (usually parked)

This is the **single on-call plan** to recover public **502**, broken UI, and unarmed automation.

---

## Phase 0 — Understand the failure (30 seconds)

| Symptom | Layer | Not the same as |
|---------|-------|-----------------|
| **502** on `https://hibs-bet.co.uk/` | nginx → gunicorn | App 500 (template error) |
| **500** on `/` or `/login` | Flask/Jinja overlay | 502 |
| **502** on `/racing/*` only | racing nginx or `:5003` | Football problem |
| Lines page RED, empty fixtures | FVE cascade from football down | Independent 502 |
| Product bar links to `127.0.0.1:5003` | Cross-links not applied | nginx |

**Golden rule:** run **one curl per URL**. Never combine two URLs with one `-w` format string.

```bash
curl -s -o /dev/null -w 'local_ping=%{http_code}\n' http://127.0.0.1:8000/api/ping
curl -s -o /dev/null -w 'local_root=%{http_code}\n' http://127.0.0.1:8000/
curl -s -o /dev/null -w 'public_login=%{http_code}\n' https://hibs-bet.co.uk/login
curl -s -o /dev/null -w 'public_racing=%{http_code}\n' https://hibs-bet.co.uk/racing/api/ping
```

**Interpretation:**

| local_ping | local_root | public_login | Diagnosis |
|------------|------------|--------------|-----------|
| 000 | — | 502 | gunicorn down (FM-01) |
| 200 | 500 | 502 or 500 | Template/overlay (FM-05) — fix before nginx |
| 200 | 200 | 502 | **nginx upstream wrong** (FM-01 cause 6/7) |
| 200 | 200 | 200 | Football GREEN |

---

## Phase 1 — One-shot full recovery (VPS)

**Primary entry point** (encodes all phases below):

```bash
sudo bash /opt/hibs-bet/scripts/vps_full_stack_recovery.sh
```

Flags:

| Flag | Use when |
|------|----------|
| `--arm-only` | Services OK; only re-install crons |
| `--skip-fve` | FVE on remote box; wire manually |
| `--skip-arm` | Repair only; don't touch crontab |

If scripts are **missing on VPS** (private repo drift), from Mac:

```bash
scp -r deploy/football-inst-overlay/scripts/*.sh \
    deploy/football-inst-overlay/deploy/apply-vps-*.sh \
    deploy/football-inst-overlay/deploy/hibs-bet.nginx.conf \
    root@87.106.100.52:/opt/hibs-bet/scripts/
# or embedded overlay (no network on VPS):
ssh root@87.106.100.52 'sudo bash /opt/hibs-bet/scripts/vps_football_apply_embedded_overlay.sh'
```

---

## Phase 2 — Ordered manual recovery (if you need control)

### Step 1 — Crontab emergency (FM-03)

Blocks all automation when www-data crontab >200 lines.

```bash
crontab -u www-data -l | wc -l   # target < 50
sudo bash /opt/hibs-bet/deploy/crontab-emergency-sports-only.sh
sudo bash /opt/hibs-bet/deploy/cron-hibs-ops-automation.sh --install
```

### Step 2 — Drift check

```bash
bash /opt/hibs-bet/scripts/verify_vps_relative_paths.sh
```

Any `MISS` → overlay not synced. Run `vps_post_overlay_sync.sh` after sync.

### Step 3 — UI overlay (FM-05 class)

Dashboard 500 = missing templates, `web_format.py`, or stale `_fixture_row_compact.html`.

```bash
sudo bash /opt/hibs-bet/scripts/vps_football_apply_embedded_overlay.sh
# or:
sudo bash /opt/hibs-bet/scripts/vps_football_fix_dashboard_500.sh
grep -n loop.index /opt/hibs-bet/templates/_fixture_row_compact.html   # must be empty
```

**UI dependency chain:**

```
.env cross-links → nginx → gunicorn → web.py context_processor
  → base.html → _product_switcher → page templates → web_format filters → static/
```

Required overlay partials: `_product_switcher.html`, `_hibs_brand.html`, `_fixture_row_compact.html`, `_portfolio_bar.html`.

### Step 4 — Football recovery (FM-01)

```bash
sudo bash /opt/hibs-bet/scripts/vps_football_hard_recovery.sh
```

Nginx-only (localhost OK, public 502):

```bash
sudo bash /opt/hibs-bet/scripts/vps_football_ensure_nginx_production.sh
sudo grep -rn '5001\|8000\|proxy_pass' /etc/nginx/sites-enabled/
```

**Must not be enabled on prod:** `hibs-unified` (`:5001` dev upstream).

### Step 5 — Cross-links + UI URLs

```bash
sudo bash /opt/hibs-bet/deploy/apply-vps-site-cross-links.sh
sudo bash /opt/hibs-bet/deploy/apply-vps-racing-link.sh
sudo systemctl restart hibs-bet
```

Sets `HIBS_RACING_BASE_URL=/racing`, `HIBS_PORTFOLIO_API_URL=/api/racing/portfolio/summary`.

### Step 6 — Racing (FM-02)

```bash
curl -s -o /dev/null -w 'racing_local=%{http_code}\n' http://127.0.0.1:5003/api/ping
sudo bash /opt/hibs-bet/scripts/vps_racing_hard_recovery.sh   # if ≠ 200
```

Do **not** curl `/cards` during bring-up.

### Step 7 — FVE / Lines (FM-04)

Football must be GREEN first.

```bash
# Remote FVE (.75):
sudo FVE_REMOTE_HOST=77.68.89.75 bash /opt/hibs-bet/deploy/apply-vps-fve-remote-host.sh
curl -sS http://77.68.89.75:8010/health | head -c 200

# Local Docker on main:
sudo bash /opt/hibs-bet/scripts/lib_fve_local_repair.sh
```

### Step 8 — Trading (FM-07 — usually parked)

Day-15 FAIL → `trading-shadow-soak` intentionally stopped. Status page only:

```bash
curl -s http://127.0.0.1:9108/live
```

### Step 9 — Arm hands-off automation

```bash
sudo bash /opt/hibs-bet/deploy/install-hibs-cron-sudoers.sh
sudo bash /opt/hibs-bet/deploy/cron-hibs-infra-fallback.sh --install
sudo bash /opt/hibs-bet/deploy/cron-hibs-ops-automation.sh --install
sudo bash /opt/hibs-bet/scripts/vps_post_overlay_sync.sh
```

### Step 10 — Verify

```bash
bash /opt/hibs-bet/scripts/verify_public_edge.sh
bash /opt/hibs-bet/scripts/verify_execution_readiness.sh
sudo bash /opt/hibs-bet/scripts/vps_industry_standard_run.sh --repair
cat /var/log/hibs-bet/three-stack-status.json
```

---

## Phase 3 — Hands-off automation target state

Once armed, these loops run **without operator intervention**:

| Loop | Schedule | Scope |
|------|----------|-------|
| **Infra fallback** | 5m | Football L1→L2→L3 + racing L2/L3 nginx |
| **Hands-off cycle** | 30m | Stack wiring, watchdog, three-stack, data producer, scrapes |
| **Racing watchdog** | 15m (root) | Soft restart if ping fails |
| **Brier circuit** | hourly | Calibration lockout FSM |
| **Racing daily** | 06:05 UTC | Cards, odds, paper settle |

### Football fallback cascade (5m)

| Level | Trigger | Action |
|-------|---------|--------|
| L0 | Every run | Probe localhost + public `/login` |
| L1 | Unit inactive / ping ≠ 200 | `systemctl restart hibs-bet` |
| L2 | Still red | `vps_football_hard_recovery.sh` |
| L3 | Localhost OK, public 502 | nginx `:8000` + `apply-vps-racing-link.sh` |

### Racing fallback (5m)

| Level | Trigger | Action |
|-------|---------|--------|
| L2 | `:5003` ping ≠ 200 | `vps_racing_hard_recovery.sh` |
| L3 | Local OK, public `/racing` 502 | `apply-vps-racing-link.sh` |

Throttles: 30–45m via `hands_off_guard` (prevents restart storms).

---

## Phase 4 — Platform matrix (all on hibs-bet.co.uk)

| Product | Public URL | Upstream | UI shell | Recovery script |
|---------|------------|----------|----------|-----------------|
| **Football** | `/`, `/login`, `/acca`… | `:8000` | `base.html` + overlay templates | `vps_football_hard_recovery.sh` |
| **Racing** | `/racing/cards` | `:5003` | racing `base.html` | `vps_racing_hard_recovery.sh` |
| **Trading** | `/harvested-execution` | `:8000` | football template | parked — monitor only |
| **Lines/FVE** | `/line-trader` | `:8000` page + `/fve-api` → FVE | `line_trader.html` | `apply-vps-fve-remote-host.sh` |

### nginx canonical config

Production: `deploy/hibs-bet.nginx.conf` only.

| Location | Upstream |
|----------|----------|
| `/` | `127.0.0.1:8000` |
| `/racing/` | `127.0.0.1:5003/` |
| `/api/racing/` | `127.0.0.1:5003/api/` |
| `/fve-api/` | `127.0.0.1:8010/` or remote FVE |

---

## Phase 5 — Industry-leading gaps (honest backlog)

| Priority | Gap | Mitigation today |
|----------|-----|------------------|
| **P0** | Private repo → no `git pull` on VPS | `vps_football_apply_embedded_overlay.sh` or Mac `scp` |
| **P0** | Scripts not on disk → crons unarmed | `verify_vps_relative_paths.sh` + `vps_post_overlay_sync.sh` |
| **P0** | `hibs-unified :5001` on prod | L3 disables + `vps_football_ensure_nginx_production.sh` |
| **P1** | Remote FVE no SSH auto-repair | Manual on `.75`; main runs `apply-vps-fve-remote-host.sh` |
| **P1** | Emergency crontab drops some jobs | Re-run `cron-hibs-ops-automation.sh --install` after emergency |
| **P2** | Trading soak parked by policy | Expected — status page only |

---

## Phase 6 — Mac deploy path (when VPS cannot pull)

```bash
# Football overlay
./scripts/link_production.sh
# or scp embedded:
scp deploy/football-inst-overlay/scripts/vps_football_apply_embedded_overlay.sh \
    root@87.106.100.52:/opt/hibs-bet/scripts/

# Racing
./scripts/deploy_racing_to_vps.sh

# Post-sync on VPS:
ssh root@87.106.100.52 'sudo bash /opt/hibs-bet/scripts/vps_post_overlay_sync.sh'
ssh root@87.106.100.52 'sudo bash /opt/hibs-bet/scripts/vps_full_stack_recovery.sh'
```

---

## Status artifacts (post-recovery)

| File | Meaning |
|------|---------|
| `/var/log/hibs-bet/three-stack-status.json` | football/racing/trading/lines flags |
| `/var/log/hibs-bet/industry-standard-status.json` | infra vs evidence gates |
| `/var/log/hibs-bet/infra-fallback.log` | 5m L1–L3 actions |
| `/var/log/hibs-bet/stack-wiring.json` | FVE proxy + cross-stack probes |

---

## Related docs

- `CODE_TO_VPS_AUTOMATION_FORENSICS.md` — pipeline audit
- `VPS_FAILURE_MODES.md` — FM-01–FM-07 registry
- `HANDS_OFF_10_10.md` — cron bundle + evidence tiers
