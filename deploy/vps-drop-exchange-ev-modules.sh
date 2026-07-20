#!/usr/bin/env bash
# Drop exchange-ev Python modules onto /opt/hibs-racing without git checkout.
#   sudo bash deploy/vps-drop-exchange-ev-modules.sh
set -euo pipefail

APP_ROOT="${APP_ROOT:-/opt/hibs-racing}"
cd "${APP_ROOT}"
mkdir -p src/hibs_racing/place deploy

cat > src/hibs_racing/place/exchange_config.py <<'PY'
"""Exchange place EV + Kelly runtime config (yaml + env overrides)."""

from __future__ import annotations

import os
from typing import Any


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, str(default)))
    except ValueError:
        return default


def exchange_runtime_config(paper_cfg: dict[str, Any] | None = None) -> dict[str, Any]:
    paper = paper_cfg or {}
    return {
        "exchange_commission": _env_float(
            "HIBS_EXCHANGE_COMMISSION", float(paper.get("exchange_commission", 0.02))
        ),
        "kelly_fraction": _env_float("HIBS_KELLY_FRACTION", float(paper.get("kelly_fraction", 0.25))),
        "max_runner_risk_pct": _env_float(
            "HIBS_MAX_RUNNER_RISK_PCT", float(paper.get("max_runner_risk_pct", 0.02))
        ),
        "exchange_ev_min_coverage_pct": _env_float(
            "HIBS_EXCHANGE_EV_MIN_COVERAGE_PCT",
            float(paper.get("exchange_ev_min_coverage_pct", 50.0)),
        ),
        "exchange_ev_min_settled": int(paper.get("exchange_ev_min_settled", 100)),
        "exchange_ev_shadow": _env_bool("HIBS_EXCHANGE_EV_SHADOW", True),
        "exchange_ev_production": _env_bool("HIBS_EXCHANGE_EV_PRODUCTION", False),
    }


def exchange_ev_shadow_enabled(paper_cfg: dict[str, Any] | None = None) -> bool:
    return bool(exchange_runtime_config(paper_cfg)["exchange_ev_shadow"])


def exchange_ev_production_enabled(paper_cfg: dict[str, Any] | None = None) -> bool:
    return bool(exchange_runtime_config(paper_cfg)["exchange_ev_production"])
PY

cat > src/hibs_racing/place/kelly.py <<'PY'
"""Fractional Kelly for pure exchange place bets."""

from __future__ import annotations


def place_kelly_fraction(
    p_place: float,
    place_decimal: float,
    *,
    commission: float = 0.02,
    kelly_fraction: float = 0.25,
    max_runner_risk_pct: float = 0.02,
) -> float:
    if place_decimal <= 1.0 or p_place <= 0.0 or p_place >= 1.0:
        return 0.0
    o_net = (place_decimal - 1.0) * (1.0 - commission)
    if o_net <= 0.0:
        return 0.0
    q = 1.0 - p_place
    raw = (p_place * o_net - q) / o_net
    if raw <= 0.0:
        return 0.0
    return min(raw * kelly_fraction, max_runner_risk_pct)
PY

cat > src/hibs_racing/place/portfolio_kelly.py <<'PY'
"""Portfolio Kelly scaling for concurrent place picks."""

from __future__ import annotations

import math

import pandas as pd

from hibs_racing.place.kelly import place_kelly_fraction


def apply_portfolio_place_kelly(
    frame: pd.DataFrame,
    *,
    pct_col: str = "kelly_place_pct",
    race_col: str = "race_id",
    raw_col: str = "_kelly_raw",
    commission: float = 0.02,
    kelly_fraction: float = 0.25,
    max_runner_risk_pct: float = 0.02,
) -> pd.DataFrame:
    if frame.empty:
        out = frame.copy()
        out[pct_col] = []
        return out

    out = frame.copy()
    raw: list[float] = []
    for _, row in out.iterrows():
        p = row.get("model_place_prob")
        o = row.get("place_decimal")
        try:
            p_f = float(p)
            o_f = float(o)
        except (TypeError, ValueError):
            raw.append(0.0)
            continue
        raw.append(
            place_kelly_fraction(
                p_f,
                o_f,
                commission=commission,
                kelly_fraction=kelly_fraction,
                max_runner_risk_pct=max_runner_risk_pct,
            )
        )
    out[raw_col] = raw

    scaled = []
    for _, group in out.groupby(race_col, sort=False):
        n = max(1, int((group[raw_col] > 0).sum()))
        factor = 1.0 / math.sqrt(n)
        scaled.extend((group[raw_col] * factor).tolist())
    out[pct_col] = [round(x * 100.0, 3) for x in scaled]
    return out.drop(columns=[raw_col], errors="ignore")
PY

cat > src/hibs_racing/place/exchange_status.py <<'PY'
"""Exchange place EV rollout status (coverage + settled sample)."""

from __future__ import annotations

from pathlib import Path

from hibs_racing.config import db_path, load_config
from hibs_racing.features.store import connect, init_db
from hibs_racing.place.exchange_config import exchange_runtime_config


def _table_columns(conn, table: str) -> set[str]:
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return {str(r[1]) for r in rows}


def exchange_ev_status(*, database: Path | None = None) -> dict:
    cfg = load_config()
    paper = cfg.get("paper", {})
    runtime = exchange_runtime_config(paper)
    db = database or db_path(cfg)
    init_db(db)

    coverage_pct = None
    priced_n = 0
    total_n = 0
    coverage_source = "card_scores.place_ev_exchange"

    with connect(db) as conn:
        cols = _table_columns(conn, "card_scores")
        if "place_ev_exchange" in cols:
            row = conn.execute(
                """
                SELECT COUNT(*) AS n,
                       SUM(CASE WHEN place_ev_exchange IS NOT NULL THEN 1 ELSE 0 END) AS priced
                FROM card_scores
                """
            ).fetchone()
        else:
            coverage_source = "upcoming_runners.offered_place_decimal"
            row = conn.execute(
                """
                SELECT COUNT(*) AS n,
                       SUM(CASE WHEN offered_place_decimal IS NOT NULL AND offered_place_decimal > 1 THEN 1 ELSE 0 END) AS priced
                FROM upcoming_runners
                """
            ).fetchone()

        if row:
            total_n = int(row[0] or 0)
            priced_n = int(row[1] or 0)
            coverage_pct = round(100.0 * priced_n / total_n, 2) if total_n else 0.0

        settled_row = conn.execute(
            """
            SELECT COUNT(*) FROM paper_bets
            WHERE backtest = 0 AND is_value_pick = 1
              AND COALESCE(paper_lane, 'production') = 'gate3'
              AND status IN ('won', 'lost', 'placed')
            """
        ).fetchone()
        settled_exchange = int(settled_row[0] or 0) if settled_row else 0

    min_cov = float(runtime["exchange_ev_min_coverage_pct"])
    min_settled = int(runtime["exchange_ev_min_settled"])
    unlock = (
        coverage_pct is not None
        and coverage_pct >= min_cov
        and settled_exchange >= min_settled
    )

    return {
        "exchange_ev_shadow": runtime["exchange_ev_shadow"],
        "exchange_ev_production": runtime["exchange_ev_production"],
        "exchange_commission": runtime["exchange_commission"],
        "kelly_fraction": runtime["kelly_fraction"],
        "max_runner_risk_pct": runtime["max_runner_risk_pct"],
        "coverage_source": coverage_source,
        "scored_runners": total_n,
        "exchange_priced_runners": priced_n,
        "exchange_place_coverage_pct": coverage_pct,
        "settled_exchange_picks": settled_exchange,
        "min_coverage_pct": min_cov,
        "min_settled_picks": min_settled,
        "production_unlock_recommended": unlock,
        "production_flip_env": "HIBS_EXCHANGE_EV_PRODUCTION=1",
        "message": (
            "Ready for operator production flip"
            if unlock
            else f"Shadow mode — need coverage>={min_cov}% and settled>={min_settled}"
        ),
    }
PY

python3 <<'PY'
from pathlib import Path

ew = Path("src/hibs_racing/place/ew_ev.py")
text = ew.read_text()
if "def exchange_place_ev" not in text:
    insert = '''

def exchange_place_ev(
    model_place_prob: float,
    place_decimal: float,
    *,
    commission: float = 0.02,
) -> float:
    if place_decimal <= 1.0 or model_place_prob < 0.0 or model_place_prob > 1.0:
        return float("nan")
    net_return = 1.0 + (place_decimal - 1.0) * (1.0 - commission)
    return model_place_prob * (net_return - 1.0) - (1.0 - model_place_prob)


'''
    anchor = "def each_way_ev("
    if anchor not in text:
        raise SystemExit("ew_ev.py layout unexpected")
    ew.write_text(text.replace(anchor, insert + anchor, 1))
    print("Patched ew_ev.py with exchange_place_ev")
else:
    print("ew_ev.py already has exchange_place_ev")
PY

echo "GREEN: exchange-ev modules installed under ${APP_ROOT}/src/hibs_racing/place/"
echo "Test:"
echo "  cd ${APP_ROOT} && source .venv/bin/activate && set -a && source .env && set +a"
echo "  PYTHONPATH=src python3 -c \"from hibs_racing.place.exchange_status import exchange_ev_status; import json; print(json.dumps(exchange_ev_status(), indent=2))\""
