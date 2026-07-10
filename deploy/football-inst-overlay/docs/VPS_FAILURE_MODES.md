# VPS failure modes registry

**Purpose:** Durable record of what keeps crashing on the four-stack VPS so automation can be updated once root-cause fixes are verified. Treat this as the postmortem backlog for industry-standard reliability work.

**Last incident window:** 2026-07-10 (football 502, racing recovered, FVE red, crontab bloat)

**Status artifacts (check after every repair):**

| File | What it tells you |
|------|-------------------|
| `/var/log/hibs-bet/three-stack-status.json` | football/racing/trading/lines green flags |
| `/var/log/hibs-bet/industry-standard-status.json` | infra vs evidence gates |
| `/var/log/hibs-bet/fve-repair.log` | FVE docker compose failures |
| `journalctl -u hibs-bet -n 60` | football gunicorn crash reason |
| `journalctl -u hibs-racing -n 60` | racing worker wedge |

---

## Active failure modes (2026-07-10)

### FM-01 — Football 502 Bad Gateway (`hibs-bet` :8000)

| Field | Detail |
|-------|--------|
| **Symptom** | `curl -sI https://www.hibs-bet.co.uk/login` → `HTTP/1.1 502 Bad Gateway`; localhost `:8000/api/ping` fails |
| **Not the same as** | Login 500 (app error) — 502 means nginx cannot reach gunicorn |
| **Root causes seen** | (1) gunicorn not listening / crash loop; (2) `HIBS_AUTH_ENABLED=1` without `HIBS_SECRET_KEY` → `init_auth()` raises at import; (3) stuck workers / accept backlog on :8000; (4) OOM during repair (~122Mi free RAM observed); (5) bad deploy overlay without restart; **(6) import OK but 502 = gunicorn never started or nginx upstream still :5001** |
| **Cascade** | FVE `hibs-bet ping failed`, fixture export count=0, line-shopper RED |
| **Manual fix** | `sudo bash /opt/hibs-bet/scripts/vps_football_hard_recovery.sh` |
| **Split diagnose** | `sudo bash /opt/hibs-bet/scripts/vps_football_diagnose_502.sh` — import OK + public 502 |
| **Code fix** | PR #62 `safe_next_url` → `index`; PR #63 hard recovery + auto `HIBS_SECRET_KEY` |
| **Automation gap** | `vps_three_stack_green.sh` only did soft restart + fixture repair; no hard kill until PR #63 |
| **Verify green** | `curl -s http://127.0.0.1:8000/api/ping` → 200; `/login` → 200 or 302 |

---

### FM-02 — Racing 502 / stuck :5003 (`hibs-racing`)

| Field | Detail |
|-------|--------|
| **Symptom** | Public `/racing/*` 502; unit may show `active` but ping ≠ 200; `accept_queue > 0` on :5003 |
| **Root causes seen** | (1) sync worker wedged on heavy `/cards` request; (2) wrong WSGI entry `hibs_racing.web:app` vs factory `create_app()`; (3) gunicorn sync workers blocking on SQLite/feature store |
| **Manual fix** | `sudo bash /opt/hibs-bet/scripts/vps_racing_hard_recovery.sh` — **do not curl /cards during bring-up** |
| **Code fix** | PR #63 `gunicorn-racing.conf.py` (gthread), `hibs-racing.service`, hard recovery committed to repo |
| **Automation gap** | Script existed on VPS but was **not in git** — drift risk |
| **Verify green** | `curl -s http://127.0.0.1:5003/api/ping` → 200; `portfolio=200` in smoke |

**Status 2026-07-10:** Recovered by industry `--repair` (1274 runners, DATA GREEN).

---

### FM-03 — Crontab bloat (www-data >200 lines)

| Field | Detail |
|-------|--------|
| **Symptom** | `cron-hibs-ops-automation.sh --install` exits: `www-data crontab bloated` (214 lines observed) |
| **Root cause** | Repeated `--install` without dedupe; duplicate managed markers (`hibs-bet:`, `hibs-racing`) |
| **Impact** | Full stack repair aborts before football recovery; cron duplication can amplify load → FM-01/FM-02 |
| **Manual fix** | `sudo bash /opt/hibs-bet/deploy/crontab-emergency-sports-only.sh` |
| **Code fix** | PR #63 auto-runs emergency during ops-automation + three-stack repair |
| **Automation gap** | Guard existed (`lib_cron_dedupe.sh`) but was **fail-closed** instead of self-healing |
| **Verify green** | `crontab -u www-data -l \| wc -l` < 50; `hibs_crontab_verify_managed` passes |

---

### FM-04 — FVE / line-shopper docker compose failure

| Field | Detail |
|-------|--------|
| **Symptom** | `[fve-repair] WARN: docker compose failed`; worker not alive; `/line-trader` RED |
| **Root causes seen** | (1) upstream football down (FM-01); (2) docker build/compose error — see `/var/log/hibs-bet/fve-repair.log`; (3) fixture cache empty when football ping fails |
| **Manual fix** | Fix football first → `sudo bash /opt/hibs-bet/scripts/lib_fve_local_repair.sh` |
| **Automation gap** | FVE repair runs even when football RED; should short-circuit or retry after FM-01 green |
| **Verify green** | `curl -s http://127.0.0.1:8010/health` → worker alive; fixtures export > 0 |

---

### FM-05 — Login 500 (app error, not 502)

| Field | Detail |
|-------|--------|
| **Symptom** | `/login` returns 500 after auth enabled |
| **Root cause** | `safe_next_url()` called `url_for("dashboard")` but endpoint is `index` |
| **Fix** | PR #62; hotfix: `sed -i 's/url_for("dashboard")/url_for("index")/g' .../auth.py` |
| **Automation gap** | No smoke test for `/login` in three-stack until PR #63 |

---

### FM-06 — API-Sports inactive / wrong quota

| Field | Detail |
|-------|--------|
| **Symptom** | Health shows `scrape_first: true`, `reason: no_api_key` or `explicit_disable`; `HIBS_API_SPORTS_HOURLY_LIMIT=400` on free tier |
| **Root cause** | Key in wrong `.env`, `HIBS_DISABLE_API_SPORTS=1`, or apply script false-negative (fixed PR key-check) |
| **Fix** | Keys in `/opt/hibs-bet/.env` only; `HIBS_API_SPORTS_HOURLY_LIMIT=4`; `sudo bash deploy/apply-vps-api-sports-free-tier.sh` |
| **Not a crash** | Degrades to scrapers; can increase cron load indirectly |

---

### FM-07 — Trading metrics amber (usually not a crash)

| Field | Detail |
|-------|--------|
| **Symptom** | `stale_feed_equity_ms` high; ready warming off-hours |
| **Expected** | Summer / off-hours; `trading-shadow-soak` active on :9108 |
| **Action** | Monitor only unless unit inactive |

---

## Dependency graph (cascade order)

```
FM-03 crontab bloat
    └── blocks ops-automation install
         └── repair incomplete

FM-01 football down (:8000)
    ├── FM-04 FVE / lines RED
    ├── FM-05 login unreachable (502 not 500)
    └── public site 502 on football routes

FM-02 racing stuck (:5003)
    └── /racing/* 502 (independent of football)
```

**Repair order:** crontab emergency → football hard recovery → racing (if needed) → FVE → full industry run.

---

## Automation update checklist (once fix verified on VPS)

Use this after a green `vps_industry_standard_run.sh --repair`:

- [ ] **Merge PR #62** (login `index` endpoint) + **PR #63** (hard recovery scripts in repo)
- [ ] **Sync both overlays** (racing + football-inst-overlay) and confirm `.deploy-revision` bumped
- [ ] **Confirm scripts on disk:** `vps_football_hard_recovery.sh`, `vps_racing_hard_recovery.sh`, `lib_racing_vps_probe.sh`
- [ ] **Crontab** < 50 lines; re-run `cron-hibs-ops-automation.sh --install` without error
- [ ] **Football smoke:** ping 200, login 200/302, `HIBS_SECRET_KEY` present if auth on
- [ ] **Racing smoke:** ping 200; do not use `/cards` in health cron (use `/api/ping` only)
- [ ] **FVE:** defer repair until football ping 200 (TODO: add guard in `lib_fve_local_repair.sh`)
- [ ] **Memory:** if `free` shows <300Mi available, reduce gunicorn workers or add swap before cron storms
- [ ] **Industry run exit:** exit 0 = infra green; exit 2 = evidence red (OK off-season)

---

## Industry-standard targets (reliability bar)

| Practice | Current | Target |
|----------|---------|--------|
| Hard recovery scripts in git | Was VPS-only for racing | Both stacks in repo (PR #63) |
| Self-healing crontab | Fail-closed | Auto emergency when >200 lines |
| Bring-up smoke | ping only | ping + login + portfolio summary |
| Cascade-aware repair | FVE runs when football down | Skip FVE until football GREEN |
| Restart throttle | 45–60m hands-off guard | Keep — prevents restart storms |
| OOM awareness | Not in automation | Preflight `free -h` in hard recovery (done) |
| Drift detection | Missing scripts caused silent skip | `verify_vps_relative_paths.sh` + this doc |

---

## Quick commands (copy-paste)

```bash
# Full repair (correct order)
sudo bash /opt/hibs-bet/deploy/crontab-emergency-sports-only.sh   # if >200 lines
sudo bash /opt/hibs-bet/scripts/vps_football_hard_recovery.sh
sudo bash /opt/hibs-bet/scripts/vps_racing_hard_recovery.sh      # only if racing ping ≠ 200
sudo bash /opt/hibs-bet/scripts/lib_fve_local_repair.sh          # after football up
sudo bash /opt/hibs-bet/scripts/vps_industry_standard_run.sh --repair

# Public verify
curl -sI https://www.hibs-bet.co.uk/login | head -1
curl -sS https://hibs-bet.co.uk/racing/api/ping
curl -sS https://hibs-bet.co.uk/line-trader | head -5
```

---

## Changelog

| Date | Event |
|------|-------|
| 2026-07-10 | Football 502 after login fix; racing hard recovery GREEN; crontab 214 lines blocked automation; FVE docker fail |
| 2026-07-10 | PR #63: football hard recovery, racing scripts to git, auto crontab emergency |
