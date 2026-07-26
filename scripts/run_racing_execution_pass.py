#!/usr/bin/env python3
"""Racing hands-off execution pass — score card → Matchbook router."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    from hibs_racing.cards.score_card import score_upcoming_cards
    from hibs_racing.cards.store import load_upcoming_runners
    from hibs_racing.live.execution_config import execution_disabled
    from hibs_racing.live.execution_router import build_execution_intents, route_execution_batch
    from hibs_racing.odds.loader import resolve_scoring_odds

    if execution_disabled():
        out = {
            "ok": True,
            "status": "disabled",
            "message": "analytics mode — set HIBS_RACING_LIVE_ROUTING_ALLOWED=1 and HIBS_RACING_CONFIRM_LIVE=YES",
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(out))
        return 0

    cards = load_upcoming_runners()
    if cards.empty:
        out = {
            "ok": True,
            "status": "no_cards",
            "intents": 0,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(out))
        return 0

    odds, _meta = resolve_scoring_odds(cards)
    frame = score_upcoming_cards(cards, odds=odds, sync_paper_ledger=False)
    if frame.empty:
        out = {
            "ok": True,
            "status": "empty_frame",
            "intents": 0,
            "ts": datetime.now(timezone.utc).isoformat(),
        }
        print(json.dumps(out))
        return 0

    intents = build_execution_intents(frame)
    report = route_execution_batch(intents, log_results=True)
    report["ok"] = report.get("errors", 0) == 0
    report["platform"] = "racing"
    report["ts"] = datetime.now(timezone.utc).isoformat()
    print(json.dumps(report, default=str))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
