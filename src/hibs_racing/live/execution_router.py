from __future__ import annotations

import os
from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol

import pandas as pd

from hibs_racing.config import load_config
from hibs_racing.live.betfair_wom import BetfairExecutionClient
from hibs_racing.live.execution_config import (
    EXECUTION_DISABLED,
    EXECUTION_DISABLED_MSG,
    betfair_enabled,
    execution_disabled,
    preferred_execution_venues,
)
from hibs_racing.odds.market_steam import evaluate_market_gauges
from hibs_racing.odds.matchbook import MatchbookClient


@dataclass
class ExecutionIntent:
    runner_id: str
    race_id: str
    horse_name: str
    course: str | None
    off_time: str | None
    stake: float
    bet_type: str
    min_odds: float | None
    offered_odds: float | None
    value_flag: bool
    kelly_multiplier: float
    steam_gate: str
    matchbook_runner_id: int | None = None
    matchbook_market_id: int | None = None
    matchbook_place_runner_id: int | None = None
    matchbook_place_market_id: int | None = None
    matchbook_event_id: int | None = None
    offered_place_odds: float | None = None
    min_place_odds: float | None = None
    betfair_market_id: str | None = None
    betfair_selection_id: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "runner_id": self.runner_id,
            "race_id": self.race_id,
            "horse_name": self.horse_name,
            "course": self.course,
            "off_time": self.off_time,
            "stake": round(self.stake, 2),
            "bet_type": self.bet_type,
            "min_odds": self.min_odds,
            "offered_odds": self.offered_odds,
            "offered_place_odds": self.offered_place_odds,
            "min_place_odds": self.min_place_odds,
            "value_flag": self.value_flag,
            "kelly_multiplier": self.kelly_multiplier,
            "steam_gate": self.steam_gate,
            "matchbook_runner_id": self.matchbook_runner_id,
            "matchbook_market_id": self.matchbook_market_id,
            "matchbook_place_runner_id": self.matchbook_place_runner_id,
            "matchbook_place_market_id": self.matchbook_place_market_id,
            "matchbook_event_id": self.matchbook_event_id,
            "betfair_market_id": self.betfair_market_id,
            "betfair_selection_id": self.betfair_selection_id,
        }


@dataclass
class ExecutionResult:
    intent: ExecutionIntent
    venue: str
    status: str  # routed | rejected | stub_ok | stub_error | skipped_duplicate
    dry_run: bool
    message: str
    external_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "venue": self.venue,
            "status": self.status,
            "dry_run": self.dry_run,
            "message": self.message,
            "external_id": self.external_id,
            "payload": self.payload,
            "intent": self.intent.to_dict(),
        }


class VenueAdapter(Protocol):
    name: str

    def available(self) -> bool: ...

    def execute(self, intent: ExecutionIntent, *, dry_run: bool) -> ExecutionResult: ...

    def execute_legs(
        self,
        intent: ExecutionIntent,
        *,
        dry_run: bool,
        database: Path | None = None,
    ) -> list[ExecutionResult]: ...


def _half_stake(stake: float) -> float:
    return round(float(stake) / 2.0, 2)


def _leg_result(
    intent: ExecutionIntent,
    *,
    venue: str,
    bet_leg: str,
    status: str,
    dry_run: bool,
    message: str,
    market_id: int | None,
    runner_id: int | None,
    odds: float | None,
    stake: float,
    external_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> ExecutionResult:
    body = dict(payload or {})
    body.update(
        {
            "bet_leg": bet_leg,
            "market-id": market_id,
            "runner-id": runner_id,
            "odds": odds,
            "stake": stake,
        }
    )
    return ExecutionResult(
        intent=intent,
        venue=venue,
        status=status,
        dry_run=dry_run,
        message=message,
        external_id=external_id,
        payload=body,
    )


class MatchbookExecutionAdapter:
    name = "matchbook"

    def __init__(self, *, client: MatchbookClient | None = None, config_path: Path | None = None) -> None:
        self._client = client
        self._config_path = config_path

    def available(self) -> bool:
        return bool(
            os.environ.get("MATCHBOOK_USERNAME", "").strip()
            and os.environ.get("MATCHBOOK_PASSWORD", "").strip()
        )

    def _client_or_none(self) -> MatchbookClient | None:
        if not self.available():
            return None
        try:
            return self._client or MatchbookClient(config_path=self._config_path)
        except Exception:
            return None

    def execute(self, intent: ExecutionIntent, *, dry_run: bool) -> ExecutionResult:
        legs = self.execute_legs(intent, dry_run=dry_run)
        if len(legs) == 1:
            return legs[0]
        ok = all(r.status in {"routed", "stub_ok", "skipped_duplicate"} for r in legs)
        routed = sum(1 for r in legs if r.status in {"routed", "stub_ok"})
        return ExecutionResult(
            intent=intent,
            venue=self.name,
            status="stub_ok" if ok else "stub_error",
            dry_run=dry_run,
            message=f"Each-way split: {routed}/{len(legs)} legs accepted",
            payload={"bet_leg": "each_way", "legs": [r.to_dict() for r in legs]},
        )

    def execute_legs(
        self,
        intent: ExecutionIntent,
        *,
        dry_run: bool,
        database: Path | None = None,
    ) -> list[ExecutionResult]:
        bet_type = (intent.bet_type or "each_way").lower()
        if bet_type == "each_way":
            return self._execute_each_way(intent, dry_run=dry_run, database=database)
        if bet_type == "place":
            return [self._execute_place_leg(intent, dry_run=dry_run, database=database)]
        return [self._execute_win_leg(intent, dry_run=dry_run, database=database)]

    def _execute_each_way(
        self,
        intent: ExecutionIntent,
        *,
        dry_run: bool,
        database: Path | None = None,
    ) -> list[ExecutionResult]:
        half = _half_stake(intent.stake)
        win_intent = replace(intent, stake=half, bet_type="win")
        place_intent = replace(intent, stake=half, bet_type="place")
        return [
            self._execute_win_leg(win_intent, dry_run=dry_run, database=database),
            self._execute_place_leg(place_intent, dry_run=dry_run, database=database),
        ]

    def _execute_win_leg(
        self,
        intent: ExecutionIntent,
        *,
        dry_run: bool,
        database: Path | None = None,
    ) -> ExecutionResult:
        if intent.matchbook_runner_id is None or intent.matchbook_market_id is None:
            return _leg_result(
                intent,
                venue=self.name,
                bet_leg="win",
                status="rejected",
                dry_run=dry_run,
                message="Missing Matchbook win runner/market ids on card row",
                market_id=intent.matchbook_market_id,
                runner_id=intent.matchbook_runner_id,
                odds=intent.offered_odds or intent.min_odds,
                stake=intent.stake,
            )
        if not dry_run:
            from hibs_racing.live.execution_log import duplicate_skip_result, live_execution_exists

            if live_execution_exists(intent.runner_id, "win", self.name, database=database):
                return duplicate_skip_result(intent, venue=self.name, dry_run=False, bet_leg="win")

        odds = intent.offered_odds or intent.min_odds
        if odds is None or odds <= 1.0:
            return _leg_result(
                intent,
                venue=self.name,
                bet_leg="win",
                status="rejected",
                dry_run=dry_run,
                message="No valid win back odds for Matchbook offer",
                market_id=intent.matchbook_market_id,
                runner_id=intent.matchbook_runner_id,
                odds=odds,
                stake=intent.stake,
            )
        return self._submit_back(
            intent,
            bet_leg="win",
            market_id=int(intent.matchbook_market_id),
            runner_id=int(intent.matchbook_runner_id),
            odds=float(odds),
            stake=float(intent.stake),
            dry_run=dry_run,
        )

    def _execute_place_leg(
        self,
        intent: ExecutionIntent,
        *,
        dry_run: bool,
        database: Path | None = None,
    ) -> ExecutionResult:
        place_market_id = intent.matchbook_place_market_id
        place_runner_id = intent.matchbook_place_runner_id or intent.matchbook_runner_id
        if place_market_id is None or place_runner_id is None:
            return _leg_result(
                intent,
                venue=self.name,
                bet_leg="place",
                status="rejected",
                dry_run=dry_run,
                message="Missing Matchbook place market/runner ids — refresh odds to map place market",
                market_id=place_market_id,
                runner_id=place_runner_id,
                odds=intent.offered_place_odds or intent.min_place_odds,
                stake=intent.stake,
            )
        if not dry_run:
            from hibs_racing.live.execution_log import duplicate_skip_result, live_execution_exists

            if live_execution_exists(intent.runner_id, "place", self.name, database=database):
                return duplicate_skip_result(intent, venue=self.name, dry_run=False, bet_leg="place")

        odds = intent.offered_place_odds or intent.min_place_odds
        if odds is None or odds <= 1.0:
            return _leg_result(
                intent,
                venue=self.name,
                bet_leg="place",
                status="rejected",
                dry_run=dry_run,
                message="No valid place back odds for Matchbook offer",
                market_id=place_market_id,
                runner_id=place_runner_id,
                odds=odds,
                stake=intent.stake,
            )
        return self._submit_back(
            intent,
            bet_leg="place",
            market_id=int(place_market_id),
            runner_id=int(place_runner_id),
            odds=float(odds),
            stake=float(intent.stake),
            dry_run=dry_run,
        )

    def _submit_back(
        self,
        intent: ExecutionIntent,
        *,
        bet_leg: str,
        market_id: int,
        runner_id: int,
        odds: float,
        stake: float,
        dry_run: bool,
    ) -> ExecutionResult:
        offer = {
            "runner-id": runner_id,
            "market-id": market_id,
            "event-id": intent.matchbook_event_id,
            "odds": round(float(odds), 2),
            "stake": round(float(stake), 2),
            "side": "back",
            "keep-in-play": False,
        }
        if dry_run:
            label = "win" if bet_leg == "win" else "place"
            return _leg_result(
                intent,
                venue=self.name,
                bet_leg=bet_leg,
                status="stub_ok",
                dry_run=True,
                message=f"Dry-run Matchbook {label} back offer (not submitted)",
                market_id=market_id,
                runner_id=runner_id,
                odds=odds,
                stake=stake,
                payload={"offer": offer, "endpoint": "POST /offers"},
            )
        client = self._client_or_none()
        if client is None:
            return _leg_result(
                intent,
                venue=self.name,
                bet_leg=bet_leg,
                status="stub_error",
                dry_run=False,
                message="Matchbook client unavailable",
                market_id=market_id,
                runner_id=runner_id,
                odds=odds,
                stake=stake,
                payload={"offer": offer},
            )
        try:
            resp = client.place_back_offer(
                market_id=market_id,
                runner_id=runner_id,
                odds=odds,
                stake=stake,
            )
            return _leg_result(
                intent,
                venue=self.name,
                bet_leg=bet_leg,
                status="routed",
                dry_run=False,
                message=f"Matchbook {bet_leg} back offer submitted",
                market_id=market_id,
                runner_id=runner_id,
                odds=odds,
                stake=stake,
                external_id=str(resp.get("offer-id") or resp.get("id") or ""),
                payload=resp,
            )
        except NotImplementedError as exc:
            return _leg_result(
                intent,
                venue=self.name,
                bet_leg=bet_leg,
                status="stub_error",
                dry_run=False,
                message=str(exc),
                market_id=market_id,
                runner_id=runner_id,
                odds=odds,
                stake=stake,
                payload={"offer": offer},
            )
        except Exception as exc:
            return _leg_result(
                intent,
                venue=self.name,
                bet_leg=bet_leg,
                status="stub_error",
                dry_run=False,
                message=str(exc),
                market_id=market_id,
                runner_id=runner_id,
                odds=odds,
                stake=stake,
                payload={"offer": offer},
            )


class BetfairExecutionAdapter:
    name = "betfair"

    def __init__(self) -> None:
        self._client: BetfairExecutionClient | None = None

    def available(self) -> bool:
        return bool(
            os.environ.get("BETFAIR_APP_KEY", "").strip()
            and os.environ.get("BETFAIR_USERNAME", "").strip()
            and os.environ.get("BETFAIR_PASSWORD", "").strip()
        )

    def execute_legs(
        self,
        intent: ExecutionIntent,
        *,
        dry_run: bool,
        database: Path | None = None,
    ) -> list[ExecutionResult]:
        return [self.execute(intent, dry_run=dry_run)]

    def execute(self, intent: ExecutionIntent, *, dry_run: bool) -> ExecutionResult:
        if intent.betfair_market_id is None or intent.betfair_selection_id is None:
            return ExecutionResult(
                intent=intent,
                venue=self.name,
                status="rejected",
                dry_run=dry_run,
                message="Missing Betfair market/selection ids (Phase C mapping not wired)",
            )
        odds = intent.offered_odds or intent.min_odds
        instruction = {
            "marketId": intent.betfair_market_id,
            "selectionId": intent.betfair_selection_id,
            "side": "BACK",
            "orderType": "LIMIT",
            "limitOrder": {
                "size": round(float(intent.stake), 2),
                "price": round(float(odds or 0), 2),
                "persistenceType": "LAPSE",
            },
        }
        if dry_run:
            return ExecutionResult(
                intent=intent,
                venue=self.name,
                status="stub_ok",
                dry_run=True,
                message="Dry-run Betfair placeOrders (not submitted)",
                payload={"instruction": instruction, "method": "SportsAPING/v1.0/placeOrders"},
            )
        if self._client is None:
            self._client = BetfairExecutionClient(
                app_key=os.environ["BETFAIR_APP_KEY"],
                username=os.environ["BETFAIR_USERNAME"],
                password=os.environ["BETFAIR_PASSWORD"],
            )
        try:
            resp = self._client.place_orders([instruction])
            return ExecutionResult(
                intent=intent,
                venue=self.name,
                status="routed",
                dry_run=False,
                message="Betfair order submitted",
                external_id=str(resp.get("betId") or resp.get("instructionReports", [{}])[0].get("betId") or ""),
                payload=resp,
            )
        except NotImplementedError as exc:
            return ExecutionResult(
                intent=intent,
                venue=self.name,
                status="stub_error",
                dry_run=False,
                message=str(exc),
                payload={"instruction": instruction},
            )
        except Exception as exc:
            return ExecutionResult(
                intent=intent,
                venue=self.name,
                status="stub_error",
                dry_run=False,
                message=str(exc),
                payload={"instruction": instruction},
            )


class ExecutionRouter:
    """Route value intents to Matchbook/Betfair adapters — dry-run by default."""

    def __init__(self, *, config_path: Path | None = None) -> None:
        cfg = load_config(config_path)
        ex = cfg.get("execution", {})
        self.dry_run = ex.get("dry_run", True) if os.environ.get("HIBS_EXECUTION_LIVE", "").strip() not in {
            "1",
            "true",
            "yes",
        } else False
        self.betfair_enabled = betfair_enabled(cfg)
        self.preferred = preferred_execution_venues(cfg)
        self.max_stake = float(ex.get("max_stake", 2.0))
        self.require_value_flag = bool(ex.get("require_value_flag", True))
        allowed_gates = {str(g).lower() for g in ex.get("allowed_steam_gates", ["proceed", "scale_up"])}
        self.allowed_gates = allowed_gates or {"proceed", "scale_up"}
        self._adapters: dict[str, VenueAdapter] = {
            "matchbook": MatchbookExecutionAdapter(config_path=config_path),
        }
        if self.betfair_enabled:
            self._adapters["betfair"] = BetfairExecutionAdapter()

    def _mapped_venue(self, intent: ExecutionIntent) -> str | None:
        for name in self.preferred:
            if name == "matchbook" and intent.matchbook_runner_id and intent.matchbook_market_id:
                return name
            if name == "betfair" and intent.betfair_market_id and intent.betfair_selection_id:
                return name
        return None

    def _select_venue(self, intent: ExecutionIntent) -> str | None:
        for name in self.preferred:
            if name == "matchbook" and intent.matchbook_runner_id and intent.matchbook_market_id:
                return name
            adapter = self._adapters.get(name)
            if not adapter:
                continue
            if name == "betfair" and intent.betfair_market_id and intent.betfair_selection_id:
                if adapter.available() or self.dry_run:
                    return name
        for name in self.preferred:
            adapter = self._adapters.get(name)
            if adapter and (adapter.available() or self.dry_run):
                return name
        return None

    def route_legs(self, intent: ExecutionIntent, *, database: Path | None = None) -> list[ExecutionResult]:
        if execution_disabled():
            return [
                ExecutionResult(
                    intent=intent,
                    venue="none",
                    status="disabled",
                    dry_run=True,
                    message=EXECUTION_DISABLED_MSG,
                )
            ]
        stake = min(float(intent.stake), self.max_stake) * float(intent.kelly_multiplier or 1.0)
        intent = replace(intent, stake=round(stake, 2))

        if self.require_value_flag and not intent.value_flag:
            return [
                ExecutionResult(
                    intent=intent,
                    venue="none",
                    status="rejected",
                    dry_run=self.dry_run,
                    message="Value flag required by execution config",
                )
            ]
        if intent.steam_gate not in self.allowed_gates:
            return [
                ExecutionResult(
                    intent=intent,
                    venue="none",
                    status="rejected",
                    dry_run=self.dry_run,
                    message=f"Steam gate '{intent.steam_gate}' blocks routing",
                )
            ]

        venue = self._select_venue(intent)
        if venue is None:
            return [
                ExecutionResult(
                    intent=intent,
                    venue="none",
                    status="rejected",
                    dry_run=self.dry_run,
                    message="No exchange venue available or mapped",
                )
            ]

        adapter = self._adapters[venue]
        if venue == "betfair" and not self.dry_run:
            from hibs_racing.live.execution_log import bet_leg_for_intent, duplicate_skip_result, live_execution_exists

            leg = bet_leg_for_intent(intent)
            if live_execution_exists(intent.runner_id, leg, venue, database=database):
                return [duplicate_skip_result(intent, venue=venue, dry_run=False)]

        return adapter.execute_legs(intent, dry_run=self.dry_run, database=database)

    def route(self, intent: ExecutionIntent, *, database: Path | None = None) -> ExecutionResult:
        legs = self.route_legs(intent, database=database)
        if len(legs) == 1:
            return legs[0]
        ok = all(r.status in {"routed", "stub_ok", "skipped_duplicate"} for r in legs)
        routed = sum(1 for r in legs if r.status in {"routed", "stub_ok"})
        return ExecutionResult(
            intent=intent,
            venue=legs[0].venue,
            status="stub_ok" if ok else "stub_error",
            dry_run=self.dry_run,
            message=f"Each-way split: {routed}/{len(legs)} legs accepted",
            payload={"bet_leg": "each_way", "legs": [r.to_dict() for r in legs]},
        )


def build_execution_intents(
    scored: pd.DataFrame,
    *,
    default_stake: float | None = None,
    gauges: list | None = None,
) -> list[ExecutionIntent]:
    """Build routable intents from scored card rows (disabled in analytics mode)."""
    if execution_disabled():
        return []
    if scored.empty:
        return []
    cfg = load_config()
    stake = default_stake if default_stake is not None else float(cfg.get("paper", {}).get("default_stake", 1.0))
    gauge_by_runner = {g.runner_id: g for g in (gauges or evaluate_market_gauges())}

    intents: list[ExecutionIntent] = []
    subset = scored[scored.get("value_flag", 0) == 1] if "value_flag" in scored.columns else scored
    mb_lookup: dict[str, dict] = {}
    if "matchbook_runner_id" not in subset.columns or subset["matchbook_runner_id"].isna().all():
        try:
            from hibs_racing.odds.matchbook import fetch_matchbook_odds

            odds, _ = fetch_matchbook_odds(scored)
            if not odds.empty:
                for rec in odds.to_dict(orient="records"):
                    mb_lookup[str(rec.get("runner_id") or "")] = rec
        except Exception:
            mb_lookup = {}

    for _, row in subset.iterrows():
        rid = str(row.get("runner_id") or "")
        gauge = gauge_by_runner.get(rid)
        mb = mb_lookup.get(rid, {})
        intents.append(
            ExecutionIntent(
                runner_id=rid,
                race_id=str(row.get("race_id") or ""),
                horse_name=str(row.get("horse_name") or ""),
                course=row.get("course"),
                off_time=row.get("off_time"),
                stake=stake,
                bet_type="each_way",
                min_odds=float(row["win_decimal"]) if pd.notna(row.get("win_decimal")) else None,
                offered_odds=float(row["win_decimal"]) if pd.notna(row.get("win_decimal")) else None,
                min_place_odds=_float_or_none(row.get("place_decimal") or row.get("offered_place_decimal") or mb.get("place_decimal")),
                offered_place_odds=_float_or_none(
                    row.get("place_decimal") or row.get("offered_place_decimal") or mb.get("place_decimal")
                ),
                value_flag=bool(row.get("value_flag")),
                kelly_multiplier=float(gauge.kelly_multiplier) if gauge else 1.0,
                steam_gate=str(gauge.gate) if gauge else "proceed",
                matchbook_runner_id=_int_or_none(row.get("matchbook_runner_id") or mb.get("matchbook_runner_id")),
                matchbook_market_id=_int_or_none(row.get("matchbook_market_id") or mb.get("matchbook_market_id")),
                matchbook_place_runner_id=_int_or_none(
                    row.get("matchbook_place_runner_id") or mb.get("matchbook_place_runner_id")
                ),
                matchbook_place_market_id=_int_or_none(
                    row.get("matchbook_place_market_id") or mb.get("matchbook_place_market_id")
                ),
                matchbook_event_id=_int_or_none(row.get("matchbook_event_id") or mb.get("matchbook_event_id")),
            )
        )
    return intents


def route_execution_batch(
    intents: list[ExecutionIntent],
    *,
    config_path: Path | None = None,
    database: Path | None = None,
    log_results: bool = False,
) -> dict[str, Any]:
    if execution_disabled():
        return {
            "ok": False,
            "status": "disabled",
            "message": EXECUTION_DISABLED_MSG,
            "mode": "analytics",
            "intents": 0,
            "results": [],
            "batch_id": None,
            "accepted": 0,
            "rejected": 0,
            "skipped_duplicate": 0,
            "dry_run": True,
        }
    import uuid

    from hibs_racing.config import db_path as resolve_db_path
    from hibs_racing.live.execution_log import append_execution_log

    router = ExecutionRouter(config_path=config_path)
    db = database or resolve_db_path(load_config(config_path))
    batch_id = str(uuid.uuid4())
    leg_results: list[ExecutionResult] = []
    for intent in intents:
        leg_results.extend(router.route_legs(intent, database=db))
    skipped = sum(1 for r in leg_results if r.status == "skipped_duplicate")
    if log_results and leg_results:
        for result in leg_results:
            bet_leg = str(result.payload.get("bet_leg") or "")
            append_execution_log(
                result,
                batch_id=batch_id,
                bet_leg=bet_leg or None,
                database=db,
            )
    report = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "batch_id": batch_id,
        "dry_run": router.dry_run,
        "betfair_enabled": router.betfair_enabled,
        "preferred_venues": router.preferred,
        "intents": len(intents),
        "legs": len(leg_results),
        "routed": sum(1 for r in leg_results if r.status in {"routed", "stub_ok"}),
        "rejected": sum(1 for r in leg_results if r.status == "rejected"),
        "skipped_duplicate": skipped,
        "errors": sum(1 for r in leg_results if r.status == "stub_error"),
        "results": [r.to_dict() for r in leg_results],
    }
    return report


def _float_or_none(value: object) -> float | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int_or_none(value: object) -> int | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
