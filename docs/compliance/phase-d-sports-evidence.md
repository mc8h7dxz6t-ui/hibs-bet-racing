# Phase D — sports evidence max (hibs-bet-racing)

**Scope:** Automatable evidence and ops in *this* monorepo.  
**Not scope:** SOC2, EU AI Act conformity, ORSA/SFCR, CPA/actuary opinions, ClaimGate, partition-enforced finance ledgers.

This is the honest equivalent of “Phase D” for the **sports research stack**, not the IG/FG/MG/CG regulatory matrices from another thread.

---

## Level model (per evidence row)

| Level | Meaning |
|-------|---------|
| **E0** | Not implemented |
| **E1** | Documented only |
| **E2** | Code + unit tests |
| **E3** | Runnable on VPS with logs |
| **E4** | Cron/systemd + verify script green + honesty plane |
| **E5** | External only (matchdays, accredited audit, partner letter) |

---

## Football forward evidence (F1–F9)

| ID | Row | Now | E target | In-repo work | Verify | E5? |
|----|-----|-----|----------|--------------|--------|-----|
| F1 | Audit log enabled | E3 | E4 | `HIBS_PREDICTION_LOG_ENABLED=1` | `verify_football_evidence_gates.sh` | |
| F2 | CLV logging | E3 | E4 | `HIBS_CLV_LOG_ENABLED=1` | same | |
| F3 | Daily pred-log cron | E3 | E4 | `cron-hibs-calibration.sh --install` | F3 line in verify | |
| F4 | Smoke / pytest | E2 | E4 | overlay tests | `pytest deploy/football-inst-overlay/tests` | |
| F5 | Production config | E2 | E4 | `institutional_readiness` | failsafe verify | |
| F6 | hibs-bet service | E2 | E4 | `hibs-bet.service` + sync | `systemctl is-active` | |
| F7 | 7d capture ≥50% | E1 | E4 | `run_forward_backfill_plan.sh`, seed cron | matchdays_7d in verify | **Yes** — needs calendar |
| F7b | Since-deploy scored capture | E1 | E4 | `HIBS_EVIDENCE_DEPLOY_DATE` | verify | **Yes** — needs data |
| F8 | CLV sample n≥25 | E1 | E4 | daily audit + sync | F8 in verify | **Yes** — needs settled rows |
| F9 | Beat-close ≥50% | E1 | E4 | same | F9 in verify | **Yes** — needs F8 |
| F9b | Shin fair CLV | E2 | E4 | informational | verify | |
| F9c | Pinnacle tier | E2 | E4 | informational | verify | |

**Football E4 done when:** F1–F6 + F3 cron green on VPS; honesty_plane on `/api/health`.  
**F7–F9 cannot reach E4 in summer gap** without matchdays — not a code failure.

---

## Racing evidence (R1–R8)

| ID | Row | Now | E target | In-repo work | Verify | E5? |
|----|-----|-----|----------|--------------|--------|-----|
| R1 | Process / DB health | E3 | E4 | `daily_refresh.sh`, systemd | `verify_racing_evidence_gates.sh` | |
| R2 | Card freshness | E3 | E4 | VPS cron | same | |
| R2b | NaN integrity | E3 | E4 | daily refresh | same | |
| R3 | Health payload | E3 | E4 | `/api/health?full=1` | same | |
| R4 | Portfolio link (overlay) | E2 | E4 | nginx proxy | racing_evidence HTTP | |
| R5 | Telemetry coverage | E2 | E4 | intraday poll post-deploy | R5 in verify | Ops |
| R6 | Paper recon clean | E2 | E4 | `daily_refresh --require-recon-clean` | same | |
| R7 | Paper sample settled | E3 | E4 | `--paper` batch | same | Calendar |
| R8 | Place Brier ≤0.25 | E3 | E4 | win-prob calibration | same | Calendar |

**Racing overlay:** HTTP `racing_evidence.py` now includes R8 (merged main).

---

## Inst++ SKUs (not four governors)

| SKU | Product | Engineering | “IL 9” equivalent here |
|-----|---------|-------------|---------------------------|
| #8 | ModelGovernor CLI | Gold in `instpp_rigorous_test.sh` | Design-partner letter — **not in repo** |
| #1 | Compliance Logger | Gold | Same |
| #5 | Webhook Mesh | Gold | Same |
| … | 12 total | See `INST_PLUS_GOLD_STANDARD.md` | Phase C = external attestation |

**Max in-repo for Inst++:** ~85–95% technical control evidence (export, verify-bundle, CI).  
**Blocked externally:** SOC2 T2, ISO certs, EU conformity, customer references.

---

## Cross-portfolio ops (hibs-bet automation)

| # | Item | Status (main) | Action |
|---|------|---------------|--------|
| 1 | `cron-hibs-calibration.sh` | **Done** | VPS `--install` |
| 2 | `cron-hibs-hands-off.sh` | **Done** | VPS `--install` |
| 3 | `cron-hibs-institutional-watchdog.sh` | **Done** | VPS `--install` |
| 4 | `run_daily_audit_pipeline` flock + fail on sync | **Done** | |
| 5 | `hibs-bet.service` Restart=on-failure | **Done** | sync deploy |
| 6 | `honesty_plane` / `stack_truth` | **Done** | |
| 7 | `verify_inst_pp_automation.sh` | **Done** | |
| 8 | Enforced Postgres partition / examiner pack | **N/A** | **Wrong product** — not in this repo |

---

## Regulatory block wall (nothing in this repo fixes)

| Block | Applies to |
|-------|------------|
| SOC 2 Type II, ISO 27001/42001 | Any “enterprise platform” claim |
| EU AI Act conformity + registration | MG/FG claims in external deck |
| SOX / CPA / actuary / ORSA / DOI exam | IG/insurance claims |
| Pen test attestation | Cyber claims |
| Phase C design-partner letter | IL 9/10 rubric in other thread |
| Proven betting ROI at exchange odds | Sports marketing |

Product can supply: **audit export, gate verify output, hash-chained Inst++ bundles, honesty_plane JSON**.  
Product cannot supply: **accredited opinions or supervisory filings**.

---

## Institutional path forward (this repo only)

```
E2 tests → E3 VPS runnable → E4 cron + verify + honesty → E5 matchdays / external certs
```

**Industry leading (honest definition here):**

- **Sports evidence:** F1–F6 + R1–R3 always green; F7–F9 + R5–R8 green over rolling windows with real data.
- **Inst++:** All rigorous CI green + one design-partner attestation per SKU you sell.
- **Not claimable:** “Regulatory compliant platform,” IL 9 on IG/FG/CG, or CyberGovernor/ClaimGate without that code existing.

---

## Diligence order (if “don’t leave doable work undone”)

1. VPS: `cron-hibs-ops-automation.sh --install` + `verify_inst_pp_automation.sh`
2. VPS: `run_forward_backfill_plan.sh` on fixture days
3. Merge/sync full `hibs-bet` repo into workspace — audit what's on `:8000` vs overlay
4. If other thread's repo exists elsewhere — **clone it** before auditing items 1–17 there
5. Do not implement ClaimGate/examiner packs in *this* repo unless that is a deliberate new product
