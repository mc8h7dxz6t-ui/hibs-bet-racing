# Code → VPS → hibs-bet: forensic automation audit

**Date:** 2026-07-11  
**Scope:** Full deploy pipeline for `hibs-bet.co.uk` (football `:8000`, racing `:5003`, FVE `:8010`)  
**Symptom under investigation:** Public **502 Bad Gateway** while localhost may be **200**

---

## Executive summary

| Layer | Industry target | Current hibs-bet state | Gap |
|-------|-----------------|----------------------|-----|
| **Source of truth** | Git `main` → reproducible artifact | Private repo; VPS cannot `git pull` or `curl` raw | **P0** — Mac `scp` / embedded overlay only |
| **Deploy path** | CI/CD or idempotent pull+restart | Partial manual patches on `/opt/hibs-bet` | Drift vs overlay branch |
| **Process manager** | systemd unit + health gate | `hibs-bet.service` → gunicorn `:8000` | OK when unit starts |
| **Edge proxy** | Single canonical nginx → `:8000` | **Drift:** `hibs-unified.conf` uses `:5001` (dev) | **P0 root cause for 502** |
| **Self-heal** | L1 soft → L2 hard → L3 nginx every 5m | Scripts exist in overlay; **not on VPS** if never synced | Automation unarmed |
| **Observability** | Split localhost vs public probes | `vps_football_diagnose_502.sh` | Use separate curls (not one `-w` for two URLs) |

**502 ≠ 500:** nginx cannot reach upstream. If `curl http://127.0.0.1:8000/api/ping` → 200 but `https://hibs-bet.co.uk/` → 502, the app is fine — **nginx upstream is wrong or SSL block missing `proxy_pass :8000`**.

---

## Pipeline map (code → live)

```mermaid
flowchart LR
  subgraph dev [Developer machine]
    GIT[Git branch / PR]
    SCP[scp embedded overlay]
    MAC[link_production.sh / deploy_racing]
  end
  subgraph vps [VPS 77.68.89.73]
    BET[/opt/hibs-bet]
    RACE[/opt/hibs-racing]
    NGINX[nginx sites-enabled]
    GUN[gunicorn :8000]
    RC[gunicorn :5003]
  end
  subgraph public [Internet]
    DNS[hibs-bet.co.uk]
  end
  GIT -->|blocked: private repo| BET
  SCP --> BET
  MAC --> RACE
  BET --> GUN
  RACE --> RC
  NGINX -->|should :8000| GUN
  NGINX -->|/racing → :5003| RC
  DNS --> NGINX
```

### Intended paths (industry standard)

| Step | Script | Frequency |
|------|--------|-----------|
| Bootstrap | `deploy/ops-bootstrap-main-vps.sh` | Once |
| Gold standard | `deploy/vps-consolidated-gold-standard.sh` | Re-run after sync |
| Overlay sync | `scripts/vps_football_apply_embedded_overlay.sh` | When git/curl blocked |
| Infra fallback | `deploy/cron-hibs-infra-fallback.sh --install` | Every 5m |
| Hands-off | `scripts/hands_off_cycle.sh` | Every 30m |
| Industry repair | `scripts/vps_industry_standard_run.sh --repair` | On demand |

### What actually runs on a drifted VPS

1. **Football code** at `/opt/hibs-bet` — may lack overlay scripts if never `scp`'d.
2. **Racing** at `/opt/hibs-racing` — **not a git clone** (no `deploy/football-inst-overlay`).
3. **nginx** may still point football to **`:5001`** (`hibs-unified`) while gunicorn binds **`:8000`**.
4. **Crons** may be bloated (>200 lines) → `cron-hibs-ops-automation.sh --install` aborts.
5. **Missing scripts** (until this PR): `apply-vps-racing-link.sh`, `apply-vps-site-cross-links.sh` — bootstrap step 5 **failed silently** when wrapped in `[[ -f ... ]]`.

---

## 502 forensic decision tree

```
https://hibs-bet.co.uk/ → 502
│
├─ curl 127.0.0.1:8000/api/ping → 000
│   └─ FM-01: gunicorn down / crash
│       → vps_football_hard_recovery.sh
│       → journalctl -u hibs-bet -n 60
│
├─ curl 127.0.0.1:8000/api/ping → 200
│   ├─ curl 127.0.0.1:8000/ → 500
│   │   └─ FM-05: template/Jinja (not 502)
│   │       → vps_football_fix_dashboard_500.sh
│   │       → grep loop.index templates/_fixture_row_compact.html
│   │
│   └─ curl 127.0.0.1:8000/ → 200
│       └─ public still 502
│           └─ FM-01 cause (6): nginx upstream :5001 or missing SSL proxy
│               → vps_football_ensure_nginx_production.sh
│               → vps_football_diagnose_502.sh
│               → grep proxy_pass /etc/nginx/sites-enabled/
```

### Diagnose commands (run separately)

```bash
curl -s -o /dev/null -w 'local_ping=%{http_code}\n' http://127.0.0.1:8000/api/ping
curl -s -o /dev/null -w 'local_root=%{http_code}\n' http://127.0.0.1:8000/
curl -sI https://hibs-bet.co.uk/login | head -3
sudo bash /opt/hibs-bet/scripts/vps_football_diagnose_502.sh
sudo grep -rn '5001\|8000\|proxy_pass' /etc/nginx/sites-enabled/
```

---

## Industry-standard automation spec (hibs-bet)

| Practice | Implementation | Status |
|----------|----------------|--------|
| **Idempotent nginx** | `deploy/hibs-bet.nginx.conf` → `:8000`; `apply-vps-racing-link.sh` | Fixed in PR |
| **502 L3 auto-fix** | `football_vps_fix_nginx_upstream` + disable `hibs-unified` | Enhanced |
| **5m infra fallback** | `lib_football_vps_fallback.sh` L1→L2→L3 | In repo; install on VPS |
| **Hard recovery** | `vps_football_hard_recovery.sh` | In repo |
| **Drift detection** | `verify_vps_relative_paths.sh` | Added |
| **No-network deploy** | `vps_football_apply_embedded_overlay.sh` | In repo |
| **Cross-product links** | `apply-vps-site-cross-links.sh` | Added |
| **Private repo sync** | GitHub token or Mac `scp` | **Still manual** |

### Automation cascade (target state)

| Level | Trigger | Action | Throttle |
|-------|---------|--------|----------|
| L0 | Every 5m | Probe ping, login, public `/login` | — |
| L1 | Unit down / ping ≠ 200 | `systemctl restart hibs-bet` | 45m |
| L2 | Still red | `vps_football_hard_recovery.sh` | 45m |
| L3 | Localhost OK, public 502 | nginx `:5001→:8000`, install `hibs-bet.nginx.conf` | 30m |
| Racing L2 | `:5003` ping ≠ 200 | `vps_racing_hard_recovery.sh` | 45m |

---

## Gaps vs industry leading (prioritized)

### P0 — Fix public 502 now (VPS)

```bash
sudo bash /opt/hibs-bet/scripts/vps_football_ensure_nginx_production.sh
# or full recovery:
sudo bash /opt/hibs-bet/scripts/vps_football_hard_recovery.sh
```

If scripts missing, from Mac:

```bash
scp deploy/football-inst-overlay/scripts/vps_football_ensure_nginx_production.sh \
    deploy/football-inst-overlay/scripts/lib_racing_vps_probe.sh \
    deploy/football-inst-overlay/deploy/apply-vps-racing-link.sh \
    deploy/football-inst-overlay/deploy/hibs-bet.nginx.conf \
    root@77.68.89.73:/opt/hibs-bet/scripts/   # adjust paths
```

### P0 — Reliable code→VPS path

- Private repo blocks `curl raw.githubusercontent.com` → use **embedded overlay** or **scp**.
- `/opt/hibs-racing` not git-backed → racing overlay never syncs from football tree.

### P1 — Arm automation on VPS

```bash
sudo bash /opt/hibs-bet/deploy/install-hibs-cron-sudoers.sh
sudo bash /opt/hibs-bet/deploy/cron-hibs-infra-fallback.sh --install
sudo bash /opt/hibs-bet/scripts/vps_industry_standard_run.sh --repair
bash /opt/hibs-bet/scripts/verify_vps_relative_paths.sh
```

### P1 — Crontab bloat (FM-03)

```bash
sudo bash /opt/hibs-bet/deploy/crontab-emergency-sports-only.sh
crontab -u www-data -l | wc -l   # target < 50
```

### P2 — Dev/prod nginx split

- `deploy/nginx/hibs-unified.conf` — **dev only** (`:5001`). Never enable on production VPS alongside `hibs-bet`.
- Production canonical: `deploy/hibs-bet.nginx.conf`.

---

## Platform matrix (all on hibs-bet.co.uk)

| Route | Upstream | Service | Public check |
|-------|----------|---------|--------------|
| `/` | `127.0.0.1:8000` | hibs-bet | `curl -sI https://hibs-bet.co.uk/` |
| `/login` | `:8000` | hibs-bet | 200 or 302 |
| `/racing/*` | `127.0.0.1:5003` | hibs-racing | `curl https://hibs-bet.co.uk/racing/api/ping` |
| `/fve-api/*` | `127.0.0.1:8010` or remote `.75` | FVE | `curl https://hibs-bet.co.uk/fve-api/health` |
| `/line-trader` | static + FVE WS | — | page loads |

**502 on `/` only** → football nginx/gunicorn. **502 on `/racing` only** → FM-02 racing.

---

## Changelog

| Date | Change |
|------|--------|
| 2026-07-11 | Added `apply-vps-racing-link.sh`, `apply-vps-site-cross-links.sh`, `vps_football_ensure_nginx_production.sh`, `verify_vps_relative_paths.sh` |
| 2026-07-11 | Enhanced `football_vps_fix_nginx_upstream` — install canonical nginx, disable `hibs-unified` |
| 2026-07-10 | FM-01..FM-07 in `VPS_FAILURE_MODES.md` |
