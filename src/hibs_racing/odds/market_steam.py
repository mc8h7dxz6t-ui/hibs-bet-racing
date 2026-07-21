from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from datetime import time as dt_time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd

from hibs_racing.cards.query import load_scored_cards
from hibs_racing.cards.store import load_upcoming_runners
from hibs_racing.config import data_dir, load_config
from hibs_racing.odds.matchbook import fetch_matchbook_odds
from hibs_racing.redis_guardrail_client import RedisGuardrailClient

LONDON = ZoneInfo("Europe/London")

_guardrail_client: RedisGuardrailClient | None = None


def _redis_guardrail() -> RedisGuardrailClient:
    global _guardrail_client
    if _guardrail_client is None:
        _guardrail_client = RedisGuardrailClient()
    return _guardrail_client


@dataclass
class SteamTrigger:
    runner_id: str
    race_id: str
    horse_name: str
    course: str | None
    off_time: str | None
    previous_odds: float
    current_odds: float
    change_pct: float
    trigger: str  # steam | drift
    detected_at: str
    drift_delta: float | None = None

    def to_dict(self) -> dict:
        return {
            "runner_id": self.runner_id,
            "race_id": self.race_id,
            "horse_name": self.horse_name,
            "course": self.course,
            "off_time": self.off_time,
            "previous_odds": round(self.previous_odds, 3),
            "current_odds": round(self.current_odds, 3),
            "change_pct": round(self.change_pct, 2),
            "drift_delta": round(self.drift_delta, 3) if self.drift_delta is not None else None,
            "trigger": self.trigger,
            "detected_at": self.detected_at,
        }


@dataclass
class MarketGauge:
    runner_id: str
    horse_name: str
    course: str | None
    off_time: str | None
    race_id: str
    opening_odds: float | None
    odds_now: float | None
    odds_20m_ago: float | None
    drift_delta: float | None
    direction: str  # steam | drift | flat | unknown
    minutes_to_off: float | None
    gate: str  # proceed | scale_up | abort
    kelly_multiplier: float
    value_flag: bool

    def to_dict(self) -> dict:
        return {
            "runner_id": self.runner_id,
            "horse_name": self.horse_name,
            "course": self.course,
            "off_time": self.off_time,
            "race_id": self.race_id,
            "opening_odds": self.opening_odds,
            "odds_now": self.odds_now,
            "odds_20m_ago": self.odds_20m_ago,
            "drift_delta": round(self.drift_delta, 3) if self.drift_delta is not None else None,
            "direction": self.direction,
            "minutes_to_off": round(self.minutes_to_off, 1) if self.minutes_to_off is not None else None,
            "gate": self.gate,
            "kelly_multiplier": self.kelly_multiplier,
            "value_flag": self.value_flag,
        }


@dataclass
class PollCycleReport:
    polled_at: str
    runners_priced: int
    pre_race_window: bool = False
    triggers: list[SteamTrigger] = field(default_factory=list)
    gauges: list[MarketGauge] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "polled_at": self.polled_at,
            "runners_priced": self.runners_priced,
            "pre_race_window": self.pre_race_window,
            "trigger_count": len(self.triggers),
            "triggers": [t.to_dict() for t in self.triggers],
            "gauges": [g.to_dict() for g in self.gauges],
            "errors": self.errors,
        }


def _state_path() -> Path:
    return data_dir() / "market_steam_state.json"


def _load_payload() -> dict:
    path = _state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _save_payload(payload: dict) -> None:
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _load_state() -> dict[str, float]:
    return {str(k): float(v) for k, v in (_load_payload().get("last_odds") or {}).items()}


def _load_history() -> dict[str, list[dict]]:
    raw = _load_payload().get("odds_history") or {}
    return {str(k): list(v) for k, v in raw.items()}


def _save_state(last_odds: dict[str, float], history: dict[str, list[dict]] | None = None) -> None:
    payload = _load_payload()
    payload["updated_at"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    payload["last_odds"] = last_odds
    if history is not None:
        payload["odds_history"] = history
    _save_payload(payload)


def _steam_cfg() -> dict:
    cfg = load_config().get("matchbook", {})
    return {
        "steam_pct": float(cfg.get("steam_threshold_pct", 8.0)),
        "drift_pct": float(cfg.get("drift_threshold_pct", 10.0)),
        "min_odds": float(cfg.get("steam_min_odds", 1.5)),
        "poll_seconds": int(cfg.get("poll_seconds", 120)),
        "pre_race_window_mins": int(cfg.get("pre_race_window_mins", 20)),
        "drift_reference_mins": int(cfg.get("drift_reference_mins", 20)),
        "drift_abort_delta": float(cfg.get("drift_abort_delta", 4.0)),
        "steam_kelly_multiplier": float(cfg.get("steam_kelly_multiplier", 1.25)),
    }


def _parse_off_dt(card_date: str | None, off_time: str | None) -> datetime | None:
    if not card_date:
        return None
    try:
        parts = str(off_time or "12:00").strip().split(":")
        hour = int(parts[0])
        minute = int(parts[1]) if len(parts) > 1 else 0
        d = datetime.strptime(str(card_date)[:10], "%Y-%m-%d")
        return datetime.combine(d.date(), dt_time(hour, minute), tzinfo=LONDON)
    except (ValueError, IndexError):
        return None


def minutes_until_off(card_date: str | None, off_time: str | None) -> float | None:
    off = _parse_off_dt(card_date, off_time)
    if off is None:
        return None
    return (off - datetime.now(LONDON)).total_seconds() / 60.0


def filter_pre_race_cards(cards: pd.DataFrame, *, window_mins: int | None = None) -> pd.DataFrame:
    """Runners with 0 <= minutes_to_off <= window (default 20)."""
    if cards.empty:
        return cards
    window = window_mins if window_mins is not None else _steam_cfg()["pre_race_window_mins"]
    keep: list[int] = []
    for idx, row in cards.iterrows():
        mins = minutes_until_off(row.get("card_date"), row.get("off_time"))
        if mins is not None and 0 <= mins <= window:
            keep.append(idx)
    return cards.loc[keep].copy() if keep else cards.iloc[0:0].copy()


def append_odds_history(
    odds: pd.DataFrame,
    *,
    polled_at: str | None = None,
    history: dict[str, list[dict]] | None = None,
    max_snapshots: int = 15,
) -> dict[str, list[dict]]:
    polled_at = polled_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    history = dict(history or _load_history())
    if odds.empty or "runner_id" not in odds.columns:
        return history
    for _, row in odds.iterrows():
        rid = str(row.get("runner_id") or "")
        if not rid:
            continue
        try:
            price = float(row["win_decimal"])
        except (TypeError, ValueError):
            continue
        snaps = history.setdefault(rid, [])
        snaps.append({"t": polled_at, "p": price})
        history[rid] = snaps[-max_snapshots:]
    return history


def drift_direction_index(
    runner_id: str,
    *,
    history: dict[str, list[dict]] | None = None,
    reference_mins: int | None = None,
) -> dict:
    """
    Δ = Odds_now − Odds_reference (20 mins ago by default).
    Negative Δ → steam (shortening); positive Δ → drift (lengthening).
    """
    reference_mins = reference_mins or _steam_cfg()["drift_reference_mins"]
    snaps = list((history or _load_history()).get(str(runner_id)) or [])
    if not snaps:
        return {"delta": None, "odds_now": None, "odds_ref": None, "direction": "unknown"}

    now_dt = datetime.now(timezone.utc)
    try:
        odds_now = float(snaps[-1]["p"])
    except (KeyError, TypeError, ValueError):
        return {"delta": None, "odds_now": None, "odds_ref": None, "direction": "unknown"}

    ref_target = now_dt - timedelta(minutes=reference_mins)
    ref_price = None
    for snap in reversed(snaps[:-1]):
        try:
            t = datetime.fromisoformat(str(snap["t"]).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t <= ref_target:
                ref_price = float(snap["p"])
                break
        except (ValueError, TypeError):
            continue
    if ref_price is None and len(snaps) >= 2:
        ref_price = float(snaps[0]["p"])

    if ref_price is None:
        return {"delta": None, "odds_now": odds_now, "odds_ref": None, "direction": "unknown"}

    delta = odds_now - ref_price
    direction = "flat"
    if delta <= -0.05:
        direction = "steam"
    elif delta >= 0.05:
        direction = "drift"
    return {"delta": delta, "odds_now": odds_now, "odds_ref": ref_price, "direction": direction}


def steam_gate_by_runner(
    runner_ids: set[str] | None = None,
    *,
    cards: pd.DataFrame | None = None,
    history: dict[str, list[dict]] | None = None,
) -> dict[str, str]:
    """
    Map runner_id → steam gate for paper/actionability (no pre-race window filter).

    ``unknown`` when no price history yet (morning Matchbook batch — typically allowed).
    """
    cfg = _steam_cfg()
    history = history or _load_history()
    cards = cards if cards is not None else load_upcoming_runners()
    out: dict[str, str] = {}
    for _, row in cards.iterrows():
        rid = str(row.get("runner_id") or "")
        if not rid:
            continue
        if runner_ids is not None and rid not in runner_ids:
            continue
        drift = drift_direction_index(rid, history=history)
        delta = drift.get("delta")
        if delta is None:
            out[rid] = "unknown"
            continue
        gate = "proceed"
        if delta <= -0.5:
            gate = "scale_up"
        if delta >= cfg["drift_abort_delta"]:
            gate = "abort"
        out[rid] = gate
    return out


def evaluate_market_gauges(
    *,
    history: dict[str, list[dict]] | None = None,
    cards: pd.DataFrame | None = None,
) -> list[MarketGauge]:
    """Drift gauges for value-flagged runners in the pre-race window."""
    cfg = _steam_cfg()
    history = history or _load_history()
    cards = cards if cards is not None else load_upcoming_runners()
    scored = load_scored_cards()
    value_ids: set[str] = set()
    if not scored.empty and "value_flag" in scored.columns:
        value_ids = set(scored.loc[scored["value_flag"] == 1, "runner_id"].astype(str))

    gauges: list[MarketGauge] = []
    for _, row in cards.iterrows():
        rid = str(row.get("runner_id") or "")
        if not rid:
            continue
        mins = minutes_until_off(row.get("card_date"), row.get("off_time"))
        if mins is None or mins < 0 or mins > cfg["pre_race_window_mins"]:
            continue

        drift = drift_direction_index(rid, history=history)
        delta = drift.get("delta")
        direction = drift.get("direction", "unknown")
        gate = "proceed"
        kelly_mult = 1.0
        if delta is not None:
            if delta <= -0.5 or direction == "steam":
                gate = "scale_up"
                kelly_mult = cfg["steam_kelly_multiplier"]
            if delta >= cfg["drift_abort_delta"]:
                gate = "abort"
                kelly_mult = 0.0

        snaps = history.get(rid) or []
        opening = float(snaps[0]["p"]) if snaps else None

        gauges.append(
            MarketGauge(
                runner_id=rid,
                horse_name=str(row.get("horse_name") or ""),
                course=row.get("course"),
                off_time=row.get("off_time"),
                race_id=str(row.get("race_id") or ""),
                opening_odds=opening,
                odds_now=drift.get("odds_now"),
                odds_20m_ago=drift.get("odds_ref"),
                drift_delta=delta,
                direction=str(direction),
                minutes_to_off=mins,
                gate=gate,
                kelly_multiplier=kelly_mult,
                value_flag=rid in value_ids,
            )
        )
    gauges.sort(key=lambda g: (g.minutes_to_off if g.minutes_to_off is not None else 999))
    return gauges


def detect_steam_drift(
    odds: pd.DataFrame,
    *,
    previous: dict[str, float] | None = None,
    history: dict[str, list[dict]] | None = None,
) -> tuple[list[SteamTrigger], dict[str, float]]:
    thresholds = _steam_cfg()
    steam_cut = thresholds["steam_pct"]
    drift_cut = thresholds["drift_pct"]
    min_odds = thresholds["min_odds"]
    prev = previous if previous is not None else _load_state()
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    triggers: list[SteamTrigger] = []
    current: dict[str, float] = dict(prev)

    if odds.empty or "runner_id" not in odds.columns:
        return triggers, current

    cards = load_upcoming_runners()
    meta = {}
    for _, row in cards.iterrows():
        rid = str(row.get("runner_id") or "")
        meta[rid] = {
            "horse_name": row.get("horse_name"),
            "course": row.get("course"),
            "off_time": row.get("off_time"),
            "race_id": row.get("race_id"),
            "card_date": row.get("card_date"),
        }

    for _, row in odds.iterrows():
        runner_id = str(row.get("runner_id") or "")
        if not runner_id:
            continue
        try:
            price = float(row["win_decimal"])
        except (TypeError, ValueError):
            continue
        if price < min_odds:
            continue

        m = meta.get(runner_id, {})
        mins = minutes_until_off(m.get("card_date"), m.get("off_time"))
        if mins is not None and (mins < 0 or mins > thresholds["pre_race_window_mins"]):
            continue

        old = prev.get(runner_id)
        current[runner_id] = price
        drift = drift_direction_index(runner_id, history=history)
        delta = drift.get("delta")

        try:
            gr = _redis_guardrail().record_odds(
                runner_id,
                feed="matchbook",
                odds=price,
                steam_threshold_pct=thresholds["steam_pct"],
                drift_threshold_pct=thresholds["drift_pct"],
            )
            if gr.get("gate") == "abort" and gr.get("direction") == "drift" and old is not None:
                triggers.append(
                    SteamTrigger(
                        runner_id=runner_id,
                        race_id=str(m.get("race_id") or row.get("race_id") or ""),
                        horse_name=str(m.get("horse_name") or row.get("horse_name") or ""),
                        course=m.get("course"),
                        off_time=m.get("off_time"),
                        previous_odds=old,
                        current_odds=price,
                        change_pct=float(gr.get("change_pct") or 0.0),
                        trigger="drift",
                        detected_at=now,
                        drift_delta=delta,
                    )
                )
                continue
        except Exception:
            pass

        if old is not None and old > 1.0:
            change_pct = 100.0 * (price - old) / old
            if change_pct <= -steam_cut:
                triggers.append(
                    SteamTrigger(
                        runner_id=runner_id,
                        race_id=str(m.get("race_id") or row.get("race_id") or ""),
                        horse_name=str(m.get("horse_name") or row.get("horse_name") or ""),
                        course=m.get("course"),
                        off_time=m.get("off_time"),
                        previous_odds=old,
                        current_odds=price,
                        change_pct=change_pct,
                        trigger="steam",
                        detected_at=now,
                        drift_delta=delta,
                    )
                )
            elif change_pct >= drift_cut:
                triggers.append(
                    SteamTrigger(
                        runner_id=runner_id,
                        race_id=str(m.get("race_id") or row.get("race_id") or ""),
                        horse_name=str(m.get("horse_name") or row.get("horse_name") or ""),
                        course=m.get("course"),
                        off_time=m.get("off_time"),
                        previous_odds=old,
                        current_odds=price,
                        change_pct=change_pct,
                        trigger="drift",
                        detected_at=now,
                        drift_delta=delta,
                    )
                )
    return triggers, current


def _poll_force() -> bool:
    return os.getenv("HIBS_MATCHBOOK_FORCE", "").strip().lower() in ("1", "true", "yes", "on")


def poll_matchbook_odds_once(
    *,
    persist: bool = True,
    pre_race_only: bool = True,
    poll_milestone: str = "pre_race_30m",
    force: bool | None = None,
) -> PollCycleReport:
    polled_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    report = PollCycleReport(polled_at=polled_at, runners_priced=0)

    cards = load_upcoming_runners()
    if cards.empty:
        report.errors.append("No upcoming cards — run fetch-cards first")
        return report

    pre_race = filter_pre_race_cards(cards)
    report.pre_race_window = not pre_race.empty
    fetch_cards = pre_race if pre_race_only and not pre_race.empty else cards
    if pre_race_only and pre_race.empty:
        report.gauges = evaluate_market_gauges(cards=cards)
        return report

    try:
        poll_force = _poll_force() if force is None else bool(force)
        odds, fetch_report = fetch_matchbook_odds(fetch_cards, force=poll_force)
        report.runners_priced = fetch_report.runners_priced
        report.errors.extend(fetch_report.errors[:5])
    except Exception as exc:
        report.errors.append(str(exc))
        return report

    if odds is None or odds.empty:
        if not report.errors:
            report.errors.append("no matchbook quotes returned")
        return report

    if "card_date" not in odds.columns:
        odds = odds.merge(fetch_cards[["runner_id", "card_date", "race_id"]], on="runner_id", how="left")
    from hibs_racing.odds.exchange_quotes import persist_exchange_quotes

    persist_exchange_quotes(odds, poll_milestone=poll_milestone, polled_at=polled_at)
    history = append_odds_history(odds, polled_at=polled_at)
    prev = _load_state()
    triggers, current = detect_steam_drift(odds, previous=prev, history=history)
    report.triggers = triggers
    report.gauges = evaluate_market_gauges(history=history, cards=cards)
    if persist:
        _save_state(current, history)
        if triggers:
            persist_triggers(triggers)
    return report


def run_matchbook_poll_loop(*, interval_seconds: int | None = None, max_cycles: int | None = None) -> None:
    interval = interval_seconds or _steam_cfg()["poll_seconds"]
    cycle = 0
    while True:
        report = poll_matchbook_odds_once(pre_race_only=True)
        print(json.dumps(report.to_dict(), indent=2))
        cycle += 1
        if max_cycles is not None and cycle >= max_cycles:
            break
        time.sleep(max(30, interval))


def latest_triggers(limit: int = 50) -> list[dict]:
    payload = _load_payload()
    return list((payload.get("recent_triggers") or [])[:limit])


def latest_gauges(limit: int = 30) -> list[dict]:
    return [g.to_dict() for g in evaluate_market_gauges()[:limit]]


def persist_triggers(triggers: list[SteamTrigger], *, keep: int = 100) -> None:
    payload = _load_payload()
    existing = latest_triggers(limit=keep)
    payload["recent_triggers"] = [t.to_dict() for t in triggers] + existing
    payload["recent_triggers"] = payload["recent_triggers"][:keep]
    _save_payload(payload)
