#!/usr/bin/env bash
# Audit racing gate hit rates — forward paper ledger + snapshot replay + live UI tiers.
#
# VPS:
#   sudo bash /opt/hibs-racing/scripts/audit_gate_hit_rates.sh
#   sudo HIBS_GATE_DAYS=90 bash /opt/hibs-racing/scripts/audit_gate_hit_rates.sh
#
# From hibs-bet wrapper:
#   sudo bash /opt/hibs-bet/scripts/audit_racing_gate_hit_rates.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "${SCRIPT_DIR}/_lib.sh"

activate_venv
load_env

DAYS="${HIBS_GATE_DAYS:-90}"
DB="${HIBS_RACING_DB_PATH}"

echo "==> racing gate hit-rate audit (forward ${DAYS}d + live card)"
echo "    db: ${DB}"
echo ""

echo "--- why experimental gates (gate3–gate11) are not in the UI ---"
python3 - <<'PY'
from hibs_racing.config import load_config

cfg = load_config()
lanes = cfg.get("paper_lanes") or {}
closure = cfg.get("gate_closure") or {}
print(f"  recommended_paper_lane: {lanes.get('recommended_paper_lane', 'gate3')}")
print(f"  live_promotion:         {lanes.get('live_promotion', False)}")
print(f"  parallel_forward:       {(lanes.get('parallel_forward') or {}).get('enabled', False)}")
print(f"  gate_closure note:      {closure.get('note', '(none)')}")
print()
print("  UI shows only: Place engine | Value lane | Sniper (Gate7) | Win engine (when calibrated)")
print("  Gate3–Gate11 log to paper_bets in parallel — replay/promotion trial, not live panels.")
PY

echo ""
echo "--- live card: runners per UI pick-quality tier (today) ---"
python3 - <<'PY'
from datetime import date

import pandas as pd

from hibs_racing.cards.query import load_scored_cards
from hibs_racing.pick_quality import classify_runner_pick_quality, runner_to_pick_context

today = date.today().isoformat()
frame = load_scored_cards()
if frame is None or frame.empty:
    print("  (no scored card — run refresh-cards first)")
else:
    sub = frame[frame["card_date"].astype(str) >= today].copy()
    if sub.empty:
        sub = frame.copy()
        print(f"  (no rows for {today}+ — showing all {len(sub)} scored runners)")
    tiers = {"watchlist": 0, "value": 0, "value_lane": 0, "paper_ready": 0, "sniper": 0, "none": 0}
    blocked: dict[str, int] = {}
    for _, row in sub.iterrows():
        r = row.to_dict()
        q = classify_runner_pick_quality(runner_to_pick_context(r))
        tier = q.get("pick_gate_tier") or "none"
        tiers[tier] = tiers.get(tier, 0) + 1
        reason = str(r.get("value_gate_reason") or "").strip()
        if reason and reason.lower() not in ("none", "nan"):
            blocked[reason] = blocked.get(reason, 0) + 1
    print(f"  runners: {len(sub)}")
    for tier, n in sorted(tiers.items(), key=lambda x: -x[1]):
        if n:
            print(f"  {tier:12} {n}")
    if blocked:
        print("  top value_gate_reason blocks:")
        for reason, n in sorted(blocked.items(), key=lambda x: -x[1])[:8]:
            print(f"    {reason}: {n}")
PY

echo ""
echo "--- forward paper ledger: hit rate / ROI per paper_lane (${DAYS}d) ---"
python3 - <<PY
import sqlite3
from pathlib import Path

db = Path("${DB}")
if not db.is_file():
    print("  ERROR: database missing")
    raise SystemExit(1)

conn = sqlite3.connect(db)
conn.row_factory = sqlite3.Row
rows = conn.execute(
    """
    SELECT COALESCE(paper_lane, 'production') AS lane,
           COUNT(*) AS total,
           SUM(CASE WHEN status = 'open' THEN 1 ELSE 0 END) AS open_n,
           SUM(CASE WHEN status != 'open' THEN 1 ELSE 0 END) AS settled,
           SUM(CASE WHEN status IN ('won', 'placed') THEN 1 ELSE 0 END) AS place_hits,
           SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) AS place_misses,
           ROUND(SUM(CASE WHEN status != 'open' THEN result_pnl ELSE 0 END), 2) AS pnl,
           ROUND(SUM(CASE WHEN status != 'open' THEN stake_units ELSE 0 END), 2) AS staked
    FROM paper_bets
    WHERE backtest = 0
      AND created_at >= date('now', ?)
    GROUP BY COALESCE(paper_lane, 'production')
    ORDER BY lane
    """,
    (f"-{int('${DAYS}')} days",),
).fetchall()

if not rows:
    print("  (no forward paper bets in window — parallel_forward may be new or refresh not run)")
else:
    print(f"  {'lane':12} {'settled':>7} {'hit%':>6} {'roi%':>7} {'pnl':>8} open")
    print(f"  {'-'*12} {'-'*7} {'-'*6} {'-'*7} {'-'*8} ----")
    for r in rows:
        settled = int(r["settled"] or 0)
        hits = int(r["place_hits"] or 0)
        misses = int(r["place_misses"] or 0)
        denom = hits + misses
        hit = (100.0 * hits / denom) if denom else None
        staked = float(r["staked"] or 0)
        pnl = float(r["pnl"] or 0)
        roi = (100.0 * pnl / staked) if staked > 0 else None
        hit_s = f"{hit:.1f}" if hit is not None else "—"
        roi_s = f"{roi:+.1f}" if roi is not None else "—"
        print(f"  {r['lane']:12} {settled:7d} {hit_s:>6} {roi_s:>7} {pnl:8.2f} {int(r['open_n'] or 0)}")
PY

echo ""
echo "--- snapshot replay (SP settled, last ${DAYS}d) ---"
if hibs-racing gate-impact --days "${DAYS}" 2>/dev/null; then
  :
else
  echo "  WARN: gate-impact unavailable — run snapshot-backfill for historical SP replay"
  echo "  hibs-racing snapshot-backfill --start YYYY-MM-DD --end YYYY-MM-DD"
fi

echo ""
echo "--- promotion status (gate_closure) ---"
python3 - <<PY
from datetime import date, timedelta

try:
    from hibs_racing.backtest.gate_impact import evaluate_lane_promotion, run_gate_impact
    from hibs_racing.config import load_config

    days = int("${DAYS}")
    end = date.today()
    start = end - timedelta(days=days)
    cfg = load_config()
    try:
        rep = run_gate_impact(start=start.isoformat(), end=end.isoformat())
        agg = rep.get("aggregate") or {}
        periods = rep.get("periods") or []
        promo = evaluate_lane_promotion(
            aggregate=agg,
            period_rows=periods,
            months_with_data=max(1, len(periods)),
            full_cfg=cfg,
        )
        for lane, info in sorted(promo.items()):
            status = "PROMOTE" if info.get("eligible") else "hold"
            roi = info.get("aggregate_roi_pct")
            picks = info.get("aggregate_picks")
            print(f"  {lane:8} {status:7} picks={picks} roi={roi}")
    except Exception as exc:
        print(f"  (snapshot replay unavailable: {exc})")
except ImportError as exc:
    print(f"  skip: {exc}")
PY

echo ""
echo "Done. Weekly institutional report: bash scripts/weekly_gate_efficacy.sh"
echo "Live actionability: /opt/hibs-bet/scripts/audit_racing_actionability.sh"
