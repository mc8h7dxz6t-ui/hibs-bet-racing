# Hibs Racing Portfolio — Deep Dive & Inst++ Roadmaps

**Generated:** 2026-06-17  
**Scope:** Every portfolio surface and gate lane in `hibs-racing`  
**Inst++ bar:** `run_institutional_check` + lane promotion gates + forward execution proof

---

## Executive Summary

The Hibs Racing portfolio is **not** a multi-sport strategy book. It is three product surfaces over one engine:

| Surface | Code | Role |
|---------|------|------|
| **Paper Ledger Portfolio** | `portfolio/racing.py` → `/portfolio` | SHA-256 verified paper P&L ledger |
| **Smart Portfolio** | `daily/smart_picks.py` | Top-3 daily value digest (UI + webhooks) |
| **Gate Lanes** | `cards/actionability.py` + `ingest/config.yaml` | Selectivity programs on the same ranker |

**Current institutional posture:** `exports/institutional_check_90d.json` → **PASSED** (78/78 snapshot days, Gate1 regression +0.35pp ROI vs raw).  
**Promotion posture:** All experimental lanes are `promotion_ready` on replay metrics but **`live_promotion: false`** — blocked on scoring-hash stability + slippage sample ≥ 300.

**Recommended paper anchor:** Gate3 (`gate_closure.recommended_paper_lane: "gate3"`).  
**Active production lane:** `flag_production` (Gate1 + Gate2 + steam + DQ≥75%) — currently identical pick set to Gate2.

---

## Inst++ Grade Definition

Inst++ = institutional checks **plus** lane-specific promotion and forward-execution proof.

### Universal Inst++ Checklist (all programs)

| # | Gate | Source | Current | Inst++ Target |
|---|------|--------|---------|---------------|
| 1 | Snapshot coverage | `institutional/check.py` | 100% (78/78) | Maintain 100% on rolling 90d |
| 2 | Gate regression | `backtest/gate_regression.py` | Gate1 ROI +0.35pp vs none | Gate1 must not degrade; Gate2 must beat Gate1 on ROI |
| 3 | Ranker profile | `cards/engine_profile.py` | enrich_48 tier | No manifest warnings in `HIBS_RACING_PRODUCTION=1` |
| 4 | Telemetry balance | `institutional/telemetry_balance.py` | Matchbook cov ≥50% | cov ≥50%, total_ms ≤120s, score share ≤92% |
| 5 | Paper reconciliation | `institutional/paper_reconciliation.py` | Advisory | `expected == ledger` value picks daily (blocking) |
| 6 | NaN integrity | `monitoring/nan_alert.py` | Passing | Zero critical NaN violations |
| 7 | Config hash stability | `snapshot_store.scoring_config_hash` | `47ca00189847dcfe` | No drift without re-snapshot + manifest |
| 8 | Slippage sample | `exchange_profiling.min_races_before_vps` | < 300 | ≥ 300 forward Matchbook races with executed quotes |
| 9 | Weekly efficacy report | `institutional/weekly_gate_efficacy.py` | Not generated | `reports/weekly_gate_efficacy.md` appended weekly |
| 10 | Shadow intents | `institutional/shadow_execution.py` | Logging daily | Intent count == production value picks per card_date |

### Lane Promotion Criteria (experimental lanes)

From `ingest/config.yaml` → `experimental_replay_lanes.promotion_criteria`:

- `min_aggregate_roi_pct`: 10.0
- `min_months_beat_gate2`: 6
- `min_months_beat_gate3`: 6
- `min_picks_per_month_gate5`: 15 (sniper volume floor)

**Hard block on live promotion (all lanes):** *"Replay-only until scoring hash stable + slippage sample >= 300."*

---

## Portfolio Map

```mermaid
flowchart TB
    subgraph Engine
        R[LightGBM Ranker]
        H[Harville EW EV]
        G[Gates 1→2→Production]
    end

    subgraph Surfaces
        PL[Paper Ledger /portfolio]
        SP[Smart Portfolio digest]
        TR[/tracker verifier]
    end

    subgraph Lanes
        P[Production flag_production]
        G3[Gate3 anchor]
        G5[Gate5 Sniper]
        G7[Gate7 True Sniper]
        G8[Gate8 Regime Blend]
    end

    R --> H --> G
    G --> P
    G --> G3
    G3 --> G5
    G3 --> G7
    G3 --> G8
    P --> PL
    P --> SP
    P --> TR
```

---

## Program 1: Paper Ledger Portfolio

**What it is:** Racing-only paper bet ledger (`build_racing_portfolio`) — `/portfolio`, `/api/portfolio`, `/api/portfolio/summary`.

**Current grade:** **Inst** (analytics mode, SHA-256 hashes, public tracker link). Not yet **Inst++** — no forward exchange execution proof, reconciliation advisory only.

### Metrics today

- Mode: `analytics` (paper only)
- Source: `place/public_tracker.py` → production value picks
- Verification: per-row `verification_hash` in meta

### Gaps vs Inst++

1. Paper ledger rows are production-lane picks, not Gate3 anchor
2. No CLV (`clv_pp: null` in normalized rows)
3. Reconciliation not blocking in institutional check
4. No lane tag on ledger rows (can't audit which program generated the bet)

### Laser-focused roadmap

| Phase | Action | Exit criteria |
|-------|--------|---------------|
| **P0 — Tag & reconcile** | Add `meta.lane` (`production` / `gate3`) to ledger rows; enable `require_recon_clean=True` in daily cron | 7 consecutive days recon-clean |
| **P1 — Gate3 paper trial** | Switch `paper_ledger` logging to Gate3 anchor while keeping production scoring live | Gate3 forward paper ROI within 15pp of replay |
| **P2 — CLV layer** | Populate `clv_pp` from Matchbook morning vs SP settlement | CLV present on ≥80% settled rows |
| **P3 — Forward proof** | 30–45 day unattended Docker cron with Matchbook quotes | `slippage_sample_size >= 300`, weekly efficacy report live |

**Inst++ exit:** Ledger tagged by lane, recon blocking, CLV on settled rows, slippage sample ≥ 300.

---

## Program 2: Smart Portfolio (Daily Digest)

**What it is:** Top-3 morning value picks (`filter_smart_picks`) — dashboard hero, Telegram/Discord/SMTP digest at 06:00.

**Filters:** `value_flag` + clear gate reason + `data_quality_pct ≥ 75` + allowed steam gates (`proceed`, `scale_up`, `unknown`).

**Current grade:** **Inst-** (same production filters as dashboard; no independent audit trail; no pick-level hash).

### Gaps vs Inst++

1. Picks are a **subset** of production lane, not Gate3 — higher noise for novice UX
2. No digest-specific verification hash or immutable morning snapshot
3. Digest can drift if cards re-score after 06:00 send
4. No performance attribution separate from full ledger

### Laser-focused roadmap

| Phase | Action | Exit criteria |
|-------|--------|---------------|
| **P0 — Freeze snapshot** | Persist `smart_picks_snapshot` JSON at digest send time with `scoring_config_hash` | Digest hash matches morning manifest |
| **P1 — Align to Gate3** | Filter from Gate3-flagged candidates only (tighter, buyer-facing) | Smart picks ⊆ Gate3 paper ledger |
| **P2 — Attribution** | Track smart-pick-only P&L cohort in `/tracker?cohort=smart` | 30d settled cohort with independent ROI |
| **P3 — Inst++ digest** | Include verification_hash + lane tag in webhook/email payload | External consumer can verify without UI |

**Inst++ exit:** Immutable morning snapshot, Gate3-aligned, independently attributable P&L cohort.

---

## Program 3: Production Lane (`flag_production`)

**What it is:** Live paper lane — Gate1 (suitability + OR) + Gate2 (confidence, regime EV, portfolio caps) + steam gate + DQ≥75%.

**Current grade:** **Inst** (active in cron, institutional check passing).

### Metrics (90d benchmark, Mar 4 – Jun 2 2026)

| Lane | Picks | Hit rate | SP ROI |
|------|-------|----------|--------|
| None | 7,686 | 26.0% | −5.4% |
| Gate1 | 5,440 | 28.0% | −5.0% |
| **Production / Gate2** | **2,442** | **34.1%** | **+48.5%** |

Steam gate currently adds **zero** pick delta vs Gate2 in this window.

### Gaps vs Inst++

1. Production ≡ Gate2 — steam gate is cosmetic until Matchbook coverage improves
2. Portfolio caps (`max_value_per_race: 2`, `max_value_per_meeting: 6`) are the main edge driver — sensitivity already proven in `gate2_sensitivity_60d.json`
3. Not the highest-ROI replay lane (Gate3 at +74.7% walkforward)

### Laser-focused roadmap

| Phase | Action | Exit criteria |
|-------|--------|---------------|
| **P0 — Hold the line** | Keep production frozen; CI gate regression on every deploy | Gate regression green 90d rolling |
| **P1 — Steam activation** | Raise Matchbook coverage to ≥50% so steam gate actually filters | Production pick delta vs Gate2 measurable |
| **P2 — Shadow parity** | `shadow_intent_count(card_date) == production value picks` | 30d shadow/ledger parity |
| **P3 — Promote Gate3** | Gate3 becomes production; current production demoted to `lane_baseline` | Walkforward Gate3 ROI holds forward 60d |

**Inst++ exit:** Steam gate materially active, shadow intents match ledger, Gate3 promotion decision executed with hash-stable re-snapshot.

---

## Program 4: Gate3 Anchor (Recommended Paper Lane)

**What it is:** Conservative anchor — tighter Gate2 (confidence 0.60, stressed EV 0.02, caps 2/4 per race/meeting).

**Current grade:** **Inst replay-ready** — `promotion_baseline: true`, recommended by `gate_closure`.

### Metrics (7-month walkforward, Nov 2025 – May 2026)

| vs Gate2 | Picks | Hit rate | SP ROI |
|----------|-------|----------|--------|
| Gate2 | 5,624 | 34.6% | +54.0% |
| **Gate3** | **3,871** | **35.7%** | **+74.7%** |
| Delta | −1,753 | +1.06pp | +20.7pp |

Gate3 beats Gate2 in **7/7** months on ROI.

### Gaps vs Inst++

1. Replay-only — not yet writing to live paper ledger
2. Blocked on slippage sample < 300
3. Note in promotion eval: *"until ranker restored"* — enrich feature coverage guard

### Laser-focused roadmap

| Phase | Action | Exit criteria |
|-------|--------|---------------|
| **P0 — Paper trial** | Log Gate3 picks to parallel ledger table / `cohort=gate3` | 30d forward paper, ≥553 picks (~Gate3 monthly rate) |
| **P1 — Slippage build** | Matchbook forward cron → `join-execution-slippage` daily | `slippage_sample_size >= 300` |
| **P2 — Stress test** | Run `slippage_stress_bps: [0, 25, 50]` on Gate3 forward sample | Gate3 ROI > 0 at 25bps stress |
| **P3 — Promote** | Set `flag_production` to Gate3 config; update `gate_closure.live_promotion: true` | Institutional check + promotion eval green |

**Inst++ exit:** Gate3 is the live paper lane with ≥300 slippage samples and positive stressed ROI.

---

## Program 5: Gate5 Sniper

**What it is:** Tighter sniper — OR≥60, RTF≥15, confidence 0.65, stressed EV 0.05, caps 1/2.

**Current grade:** **Inst replay-promotion_ready** — all promotion checks pass; `live_promotion: false`.

### Metrics (walkforward aggregate)

| Metric | Value |
|--------|-------|
| Picks | 1,958 (~280/mo) |
| Hit rate | 38.4% |
| SP ROI | **+116.7%** |
| vs Gate3 | Beats G3 in 7/7 months |

### Gaps vs Inst++

1. Same hard block: slippage + hash stability
2. Higher variance — monthly pick count can dip in thin months
3. No independent shadow strategy_id (`HIBS_RACING_GATE5`)

### Laser-focused roadmap

| Phase | Action | Exit criteria |
|-------|--------|---------------|
| **P0 — Shadow lane** | `log_shadow_intents(..., strategy_id="HIBS_RACING_GATE5")` on Gate5-flagged rows | Daily intent log |
| **P1 — Volume monitor** | Alert if `avg_picks_per_dense_month < 15` | No month below sniper floor |
| **P2 — Forward paper** | Parallel cohort after Gate3 promotion stable | 60d Gate5 cohort ROI > Gate3 |
| **P3 — Selective promote** | Gate5 as **overlay** (max 1 pick/meeting) not full production replacement | Buyer-facing "sniper tier" with separate tracker |

**Inst++ exit:** Independent shadow + paper cohort with 60d forward ROI beating Gate3 and volume floor maintained.

---

## Program 6: Gate6 Market-Bounded

**What it is:** SP band 2.0–10.0, OR≥50, caps 2/4 — expansion lane bounded by price.

**Current grade:** **Inst replay-FAIL** — `promotion_ready: false` (0/7 months beat Gate3).

### Metrics

| Metric | Value |
|--------|-------|
| Picks | 3,131 |
| Hit rate | 55.3% (short-price bias) |
| SP ROI | +22.5% |
| vs Gate3 | **Fails** aggregate and monthly |

### Laser-focused roadmap

| Phase | Action | Exit criteria |
|-------|--------|---------------|
| **P0 — Freeze** | Mark `gate_closure` as exhausted for Gate6 — no further param search | Documented retire decision |
| **P1 — Mine insights** | Extract `blocked_reasons` / price-band analytics for Gate8 regime logic | Report only |
| **P2 — Archive** | Remove from active walkforward CI; keep replay export for DD | Zero cron compute on Gate6 |

**Inst++ exit:** **Do not promote.** Gate6 is a negative-result lane — valuable for DD transparency only.

---

## Program 7: Gate7 True Sniper

**What it is:** Strictest sniper — OR≥65, RTF≥20, confidence 0.65, caps **1/1**.

**Current grade:** **Inst replay-promotion_ready** — highest replay ROI in portfolio.

### Metrics (walkforward aggregate)

| Metric | Value |
|--------|-------|
| Picks | 1,003 (~143/mo) |
| Hit rate | 39.2% |
| SP ROI | **+178.5%** |
| vs Gate3 | Beats G3 in 7/7 months |

### Gaps vs Inst++

1. Thin pool — PnL units lower than Gate3 despite higher ROI% (−1,099 units vs G3 in walkforward)
2. Same slippage/hash block
3. Risk: overfitting to high-confidence tail

### Laser-focused roadmap

| Phase | Action | Exit criteria |
|-------|--------|---------------|
| **P0 — PnL-aware eval** | Add promotion criterion: `min_pnl_units_vs_gate3` (not just ROI%) | Gate7 must not sacrifice >X% absolute units |
| **P1 — Shadow** | `strategy_id="HIBS_RACING_GATE7"` shadow intents | Daily log |
| **P2 — OOS extend** | Re-run walkforward through Jun 2026 full month | 8/8 months beat Gate3 |
| **P3 — Premium tier** | Gate7 as optional "high conviction" digest pick (max 1/day in Smart Portfolio) | Smart Portfolio Gate7 pick ≤1, 30d attribution |

**Inst++ exit:** Shadow lane live, PnL floor met, 8-month OOS confirmation, optional premium digest tier.

---

## Program 8: Gate8 Regime Blend

**What it is:** Dynamic caps from confidence — base Gate3, escalates to 1/2 caps when confidence < 0.70.

**Current grade:** **Inst replay-promotion_ready** — strong ROI with better PnL units than Gate7.

### Metrics (walkforward aggregate)

| Metric | Value |
|--------|-------|
| Picks | 1,986 (~284/mo) |
| Hit rate | 38.5% |
| SP ROI | **+147.6%** |
| PnL units vs Gate3 | **+41.1** (only experimental lane with positive unit delta vs G3) |

### Gaps vs Inst++

1. Regime trigger logic needs forward validation (confidence distribution may shift)
2. More complex than Gate3 — harder to explain to buyers
3. Same slippage/hash block

### Laser-focused roadmap

| Phase | Action | Exit criteria |
|-------|--------|---------------|
| **P0 — Regime audit** | Log `regime_state` (default vs escalated) per pick in ledger_events | 30d regime distribution stable |
| **P1 — A/B paper** | Gate3 vs Gate8 parallel cohorts (same hash window) | Gate8 units ≥ Gate3 at ≥90% of Gate3 ROI |
| **P2 — Promote candidate** | If P1 passes, Gate8 becomes promotion candidate **ahead of** Gate5/7 | `gate_closure.recommended_paper_lane: "gate8"` |
| **P3 — Inst++** | Full promotion after slippage ≥ 300 | Same as Gate3 P3 |

**Inst++ exit:** Gate8 forward paper beats Gate3 on **absolute PnL units** with slippage proof — best candidate to supersede Gate3 anchor.

---

## Program 9: Shadow Execution (`HIBS_RACING_PRODUCTION`)

**What it is:** `log_shadow_intents` — BetIntent-shaped audit rows at morning odds, no broker routing.

**Current grade:** **Inst-** (logging exists in `refresh.py`; no parity enforcement).

### Laser-focused roadmap

| Phase | Action | Exit criteria |
|-------|--------|---------------|
| **P0 — Parity check** | Daily: `shadow_intent_count == production value picks` | 30d zero mismatch |
| **P1 — Multi-lane shadows** | Separate strategy_ids for Gate3, Gate5, Gate7, Gate8 | Per-lane intent counts in manifest |
| **P2 — Execution bridge** | Wire to Matchbook place API (disabled flag) when slippage ≥ 300 | Dry-run orders logged, not sent |
| **P3 — Live shadow** | Real orders at min stake with kill switch | 45d forward with institutional check green |

**Inst++ exit:** Multi-lane shadow parity + optional live micro-stake with full audit chain.

---

## Program 10: Observation Lane (`HIBS_OBSERVATION_LANE=1`)

**What it is:** Model/gate freeze mode — softer institutional checks, no weekly retrain.

**Current grade:** **Operational tool** — not a betting program.

### Laser-focused roadmap

| Phase | Action | Exit criteria |
|-------|--------|---------------|
| **P0 — Use correctly** | Enable only during buyer demo / VPS burn-in | Documented in `DOCKER.md` |
| **P1 — Exit criteria** | Disable when Gate3 paper trial starts | `HIBS_OBSERVATION_LANE=0` in production `.env` |
| **P2 — Never live** | Observation lane must not be used with real capital | Enforced in `institutional/check.py` blocking set |

**Inst++ exit:** Observation lane retired before any live promotion.

---

## Master Sequencing (Portfolio-Wide)

Execute in this order — each step unlocks the next:

```
1. SLIPPAGE BUILD (Matchbook forward cron, Docker VPS)
   └─ Target: slippage_sample_size >= 300

2. GATE3 PAPER TRIAL (parallel cohort, recon blocking)
   └─ Target: 30d forward Gate3 ROI within replay tolerance

3. WEEKLY EFFICACY (reports/weekly_gate_efficacy.md)
   └─ Target: SP vs executed ROI + slippage bps per lane

4. SMART PORTFOLIO ALIGN (Gate3 + frozen digest snapshot)
   └─ Target: digest ⊆ Gate3 paper ledger

5. GATE8 A/B (if units beat Gate3 forward)
   └─ Target: gate_closure → gate8 OR stay gate3

6. SNIPER TIERS (Gate5/7 as overlay, not production replacement)
   └─ Target: premium digest tier, separate attribution

7. LIVE PROMOTION (gate_closure.live_promotion: true)
   └─ Target: institutional check ALL blocking + slippage proof
```

---

## Quick Reference: Lane Promotion Status

| Lane | Replay ROI | promotion_ready | live_promotion | Inst++ path |
|------|-----------|-----------------|----------------|-------------|
| Production/Gate2 | +48.5% (90d) | n/a (baseline) | active paper | Hold → migrate to Gate3 |
| Gate3 | +74.7% (WF) | baseline | **false** | **Primary promotion target** |
| Gate5 | +116.7% | true | false | Overlay after Gate3 stable |
| Gate6 | +22.5% | **false** | false | **Retire** |
| Gate7 | +178.5% | true | false | Premium tier / overlay |
| Gate8 | +147.6% | true | false | **Best Gate3 successor candidate** |

WF = 7-month walkforward (`exports/gate_lane_walkforward.json`)

---

## Commands

```bash
# Institutional check (production)
hibs-racing institutional-check --days 90

# Gate walkforward + promotion eval
hibs-racing gate-lane-walkforward --start 2025-11-01 --end 2026-05-31

# Weekly efficacy report
hibs-racing weekly-gate-efficacy --append

# Slippage join (forward)
hibs-racing join-execution-slippage --days 14

# Portfolio API
curl -s http://127.0.0.1:5003/api/portfolio/summary | jq .
```

---

## Related Docs

- `DATA_ROOM.md` — buyer positioning and CSV exports
- `ACQUIRE_LISTING.md` — institutional performance matrix
- `docs/TECHNICAL_DUE_DILIGENCE_FAQ.md` — buyer Q&A
- `exports/institutional_check_90d.json` — latest check snapshot
- `exports/gate_lane_walkforward.json` — lane promotion evaluation
- `exports/production_benchmark_90d.json` — production vs gate benchmarks
