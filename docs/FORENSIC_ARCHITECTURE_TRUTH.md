# Forensic architecture truth — diligence auditor sheet

**Purpose:** Honest mapping of what exists in `hibs-bet-racing` vs external “enterprise platform” rebrands.  
**Audience:** Technical due diligence, internal governance, VPS operators.  
**Not for:** VC pitch decks without this disclaimer attached.

---

## Verdict (matches independent forensic review)

The sports stack and the Inst++ CLI portfolio **share a git monorepo** but are **not the same product**. External documents that map:

| External rebrand | Real system in this repo |
|------------------|--------------------------|
| ModelGovernor `:8080` | Football **hibs-bet** `:8000` (separate app; overlay in `deploy/football-inst-overlay/`) |
| FinanceGovernor `:8090` | Racing **hibs-racing** `:5003` (`src/hibs_racing/`) |
| CyberGovernor `:8120` | FVE line shopper `:8010` (external `football-app` Docker) |
| AlgoFreeze `:8094` | Trading shadow `:9108`–`:9110` (frozen `EXECUTION_DISABLED`) |
| ClaimGate `:8103` | **Does not exist** in codebase |

**Ports 8090, 8094, 8103, 8120, 5433, 5434** — zero references in this repository.

**“Four isolated PostgreSQL databases”** — not substantiated. Operational reality:

- **SQLite** on VPS: `feature_store.sqlite`, `prediction_audit.sqlite`, per-SKU `*.sqlite`
- **Optional Postgres** DSN for Inst++ compliance/spend ledgers (design-partner profile only)
- **Three isolated deploy roots**: `/opt/hibs-bet`, `/opt/hibs-racing`, `/opt/trading-core`

---

## What is real (runnable + tested)

| Component | Port | Code | Storage |
|-----------|------|------|---------|
| Racing engine | 5003 | `src/hibs_racing/` | SQLite `feature_store.sqlite` |
| Football audit overlay | 8000 | `deploy/football-inst-overlay/` | SQLite `prediction_audit.sqlite` (on hibs-bet host) |
| FVE / lines | 8010 | External `football-app` | Host-specific |
| Trading shadow | 9108–9110 | `trading_core/` in overlay | Metrics only; execution frozen |
| Inst++ 12 SKUs | 8790 (Proof Console) | `src/inst_workflow/`, `model_governor/`, etc. | SQLite default; Postgres optional |
| ModelGovernor (#8) | CLI | `src/model_governor/` | `model_governor.sqlite` + inst_spine |

**ModelGovernor** is a real tamper-evident lifecycle CLI — it is **not** the football web app on port 8000.

**FinanceGovernor / Insurance Governor** are **sales bundle labels** (SKU combinations), not runnable services.

---

## Code logic vs labels (PE diligence failure modes)

Opening Python on this repo reveals:

- Horse racing: `overround`, `steam`, `Harville`, `paper_bets`, `feature_store`
- Football: `fixture_id`, `1X2`, `CLV`, `prediction_snapshots`, `league_code`
- Execution: `EXECUTION_DISABLED = True` hardcoded in `execution_config.py`

There is **no** SOC2 Type II, ISO 27001, or penetration-test certification in tree.  
`docs/SOC2_VPC_DILIGENCE_PACK.md` is a **template**, not an attestation.

---

## Evidence math — three CLV definitions (do not conflate)

| Metric | Module | Binding for `buyer_ready`? |
|--------|--------|----------------------------|
| **F9 raw implied beat-close** | `prediction_log.clv_beat_close_summary` | **Yes** (football) |
| **F9b Shin fair-line CLV** | `price_truth.clv_beat_close_fair_summary` | **No** (informational) |
| **Institutional edge CLV %** | `clv_institutional.enrich_clv_price_truth` | Display / research |

F9 CLV is tied to the **value `best_bet` leg**, not generic `predicted_outcome`.

---

## `buyer_ready` parity fixes (this branch)

| Issue | Fix |
|-------|-----|
| Racing overlay omitted R8 place Brier | `racing_evidence.py` now includes **R8_place_brier** |
| Truth plane `win_brier` always null | Uses `brier_score` from `settled_paper_calibration()` |
| R7 counted open bets | Prefers **settled** paper rows |
| Informational F9b/F9c inflated score | `score_gates()` skips `informational` gates |
| Brier ignored `probabilities_pct` | `_metrics_for_rows()` uses `model_probs_from_prediction()` |

Live surface: `/api/health` → `stack_truth` block via `hibs_predictor.stack_truth`.

---

## Completion % claims

“71–78% complete” across football/racing is an **engineering estimate**, not audited LOC coverage.  
Calendar-bound gates (F7–F9 football, R8 racing) require **live matchdays + settled rows** — code cannot green them in summer gaps.

---

## Operator commands

```bash
# Honest stack map (JSON)
PYTHONPATH=deploy/football-inst-overlay/src python3 -c \
  "from hibs_predictor.stack_truth import stack_truth_summary; import json; print(json.dumps(stack_truth_summary(), indent=2))"

# Football evidence (VPS)
bash deploy/football-inst-overlay/scripts/verify_football_evidence_gates.sh

# Racing evidence (local)
bash scripts/verify_racing_evidence_gates.sh
```

---

## Commercial honesty

- **Sports stack commercial value** to generic enterprise buyers: **low** without disclosed domain (betting research).
- **Inst++ SKU value** to fintech/legal buyers: **pilot-scale CLI tooling** with offline `verify-bundle` — not a managed SaaS platform.
- **Misrepresentation risk**: Selling this repo as CyberGovernor/ClaimGate/AlgoFreeze without code rename is **due-diligence fatal**.

Use `stack_truth` and this document in every data room.
