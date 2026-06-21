# Inst++ completion ladder

**Target:** engineering **A**, evidence **A**, nine-ten **≥8.5 avg** (7/8 pillars ≥9).  
**Run status:** `./scripts/score_hibs_nine_ten.sh --remote` · `./scripts/verify_football_evidence_gates.sh`

---

## Grade map (honest)

| Grade | Meaning | You are here when… |
|-------|---------|-------------------|
| **D** | Red | F1–F3 fail (audit/CLV/cron off) |
| **C / C+** | Amber | Engineering OK; evidence gates open |
| **B / B+** | Strong | F3 green; F7 partial; F8 accumulating |
| **A** | Institutional | `buyer_ready=true` (all F1–F9) |
| **9/10 stack** | Buyer conversations | A + production verify + data room export |

---

## Tier 0 — Today (no matchdays required)

| # | Action | Moves | Command |
|---|--------|-------|---------|
| 0.1 | Merge + deploy | production, racing URL, paper | `./scripts/deploy_vps_main_stack.sh` |
| 0.2 | **Engineering A one-shot** | zero config warnings | `sudo bash deploy/apply-vps-engineering-grade-a.sh` |
| 0.3 | Auto cron on deploy | **F3** → PASS | Wired in `_deploy_vps_post.sh` after merge |
| 0.4 | Evidence deploy date | F7b window | Set in `.env` on first deploy (auto) |
| 0.5 | Seed snapshots (API) | **matchdays_7d** ↑ | `./scripts/seed_forward_evidence.sh` |
| 0.6 | Green loop | visibility | `DEPLOY_HOST=87.106.100.52 ./scripts/green_forward_evidence.sh --remote --seed` |

**Expected after Tier 0:** engineering **A** (if auth + calib cache green), evidence **C+**, nine-ten **~7.5–8**.

```bash
# Verify engineering A (exit 0 = zero warnings + grade A)
bash scripts/verify_engineering_grade_a.sh
PYTHONPATH=src python3 scripts/validate_institutional_config.py --grade-a
```

---

## Tier 1 — This week (fixture days)

| # | Action | Moves | Command |
|---|--------|-------|---------|
| 1.1 | Dashboard login on matchdays | F7 capture live | Load `/` while logged in |
| 1.2 | Daily cron runs | F8 rows accumulate | `tail /var/log/hibs-bet/daily-audit-am.log` |
| 1.3 | pred-log-sync after FT | CLV join | Automatic via cron |
| 1.4 | Racing VPS cron | racing pillar 9 | `./scripts/install_racing_vps_cron.sh` |

**Expected after Tier 1 (≥3 matchdays):** F7 can PASS if capture ≥50%; F8 still building.

---

## Tier 2 — Evidence green (calendar)

| # | Gate | Pass when |
|---|------|-----------|
| 2.1 | **F7** | ≥3 matchdays + 7d capture ≥50% |
| 2.2 | **F7b** | Since-deploy scored capture ≥80% |
| 2.3 | **F8** | ≥25 CLV rows (28d) |
| 2.4 | **F9** | Beat-close ≥50% on those rows |

```bash
./scripts/green_forward_evidence.sh --remote --watch
```

**Expected:** evidence **A**, `buyer_ready=true`, Inst++ chip **B2B ✓**.

---

## Tier 3 — Buyer-ready (deal room)

| # | Deliverable | Command |
|---|-------------|---------|
| 3.1 | Data room folder | `./scripts/export_b2b_data_room.sh` |
| 3.2 | Live chip screenshot | `data/b2b_data_room/SCREENSHOT_INSTRUCTIONS.txt` |
| 3.3 | Buyer memo | `docs/FOOTBALL_BUYER_MEMO.md` |
| 3.4 | SLA signed | `docs/B2B_SUPPORT_SLA_TEMPLATE.md` |

---

## What does NOT move the grade (avoid distraction)

- Model tuning / gate threshold changes **during** the first evidence window (see [CLV_RECOVERY_PLAYBOOK.md](./CLV_RECOVERY_PLAYBOOK.md) for **post-F9-fail** iteration)
- Trading promotion or micro-live
- Multi-tenant SaaS features
- Historic backfill ROI claims without forward gates
- Merging PRs without deploying (code ≠ production grade)

---

## Tier 2b — Post-30d CLV recovery (F8 green, F9 red)

| # | Action | When |
|---|--------|------|
| 2b.1 | Diagnose cohort | F9 fails with n≥25 |
| 2b.2 | Offline gate compare | `./scripts/inst_pp_clv_recovery_cycle.sh --compare` |
| 2b.3 | Promote if eligible | `deploy/apply-vps-gate-profile.sh <profile> --new-evidence-date` |
| 2b.4 | Re-prove forward only | `./scripts/green_forward_evidence.sh --watch` |

Full protocol: [CLV_RECOVERY_PLAYBOOK.md](./CLV_RECOVERY_PLAYBOOK.md).

---

## Pillar nudges (nine-ten)

| Pillar | Quick nudge |
|--------|-------------|
| football_engineering | `validate_institutional_config.py` green; reduce prod warnings |
| football_evidence | Tiers 0–2 above |
| football_production | `link_production.sh` + `--remote` score |
| racing_integration | VPS cron + URL patch |
| trading_ops | paper :9109 `/ready` NODE_READY |
| stack_boundaries | `verify_stack_boundaries.sh` |
| b2b_packaging | export data room |
| ops_automation | `sudo bash scripts/install_hands_off_automation.sh` (hands-off + Inst++ verify) |

---

## Tier 0b — Hands-off Inst++ (automated)

| # | Action | Moves | Command |
|---|--------|-------|---------|
| 0b.1 | One-shot VPS arming | all crons + hands-off | `sudo bash scripts/install_hands_off_automation.sh` |
| 0b.2 | Inst++ verify | automation_health green | `bash scripts/verify_inst_pp_automation.sh` |
| 0b.3 | Weekly snapshot | nine-ten + data room | auto Sun 08:00 UTC (`cron-hibs-inst-pp-weekly.sh`) |

**Expected after Tier 0b:** ops_automation pillar **≥8**; `inst_pp_tier` **institutional_engineering** when engineering **A/B+** and crons fresh.

---

## Daily 30-second check

```bash
curl -sS https://hibs-bet.co.uk/api/health | python3 -c "
import sys,json
d=json.load(sys.stdin)
ir=d.get('institutional_readiness',{})
ao=d.get('audit_ops',{})
fwd=ao.get('forward_evidence',{})
print('Eng',ir.get('engineering_grade'),'Ev',ir.get('evidence_grade'),
      'buyer_ready',fwd.get('buyer_ready'),'matchdays',fwd.get('matchdays_7d'),
      'cron',(ao.get('pred_log_sync_cron') or {}).get('scheduled'))
"
```
