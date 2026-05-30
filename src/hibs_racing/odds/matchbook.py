from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from datetime import time as dt_time
from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.config import load_config
from hibs_racing.entity.natural_key import generate_natural_key
from hibs_racing.entity.timezone import LONDON, matchbook_event_local_date, normalize_matchbook_time_to_london
from hibs_racing.odds.matching import horse_names_match

HORSE_RACING_SPORT_ID = 24735152712200


@dataclass
class MatchbookFetchReport:
    races_attempted: int = 0
    races_matched: int = 0
    runners_priced: int = 0
    events_loaded: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "races_attempted": self.races_attempted,
            "races_matched": self.races_matched,
            "runners_priced": self.runners_priced,
            "events_loaded": self.events_loaded,
            "errors": self.errors,
        }


def _credentials() -> tuple[str, str]:
    user = os.environ.get("MATCHBOOK_USERNAME", "").strip()
    password = os.environ.get("MATCHBOOK_PASSWORD", "").strip()
    if not user or not password:
        raise ValueError("Set MATCHBOOK_USERNAME and MATCHBOOK_PASSWORD in .env")
    return user, password


def _api_base(cfg: dict) -> str:
    return os.environ.get("MATCHBOOK_API_BASE") or cfg.get("matchbook", {}).get(
        "api_base", "https://api.matchbook.com/edge/rest"
    ).rstrip("/")


class MatchbookClient:
    """Matchbook REST client — session token auth (~6h lifetime)."""

    def __init__(
        self,
        *,
        username: str | None = None,
        password: str | None = None,
        api_base: str | None = None,
        config_path: Path | None = None,
    ) -> None:
        try:
            import requests
        except ImportError as exc:
            raise ImportError('Install api extra: pip install -e ".[api]"') from exc

        cfg = load_config(config_path)
        mb = cfg.get("matchbook", {})
        if username and password:
            self._username, self._password = username, password
        else:
            self._username, self._password = _credentials()
        self._api_base = (api_base or _api_base(cfg)).rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": mb.get("user_agent", "hibs-racing/0.1"),
            }
        )
        self._token: str | None = None
        self._token_at: float = 0.0
        self._sport_id = int(mb.get("sport_id", HORSE_RACING_SPORT_ID))

    def login(self, *, force: bool = False) -> str:
        if self._token and not force and (time.time() - self._token_at) < 5 * 3600:
            return self._token
        url = f"{self._api_base}/security/session"
        resp = self._session.post(
            url,
            json={"username": self._username, "password": self._password},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        token = payload.get("session-token") or payload.get("session_token")
        if not token:
            raise ValueError("Matchbook login response missing session-token")
        self._token = str(token)
        self._token_at = time.time()
        self._session.headers["session-token"] = self._token
        return self._token

    def _get(self, path: str, params: dict | None = None) -> dict:
        self.login()
        url = f"{self._api_base}/{path.lstrip('/')}"
        resp = self._session.get(url, params=params or {}, timeout=45)
        resp.raise_for_status()
        return resp.json()

    def fetch_horse_events(
        self,
        *,
        after_ts: int | None = None,
        before_ts: int | None = None,
        include_prices: bool = True,
    ) -> list[dict]:
        params: dict[str, Any] = {
            "sport-ids": str(self._sport_id),
            "per-page": "200",
            "offset": "0",
            "states": "open,suspended",
            "odds-type": "DECIMAL",
            "include-prices": "true" if include_prices else "false",
            "price-depth": "1",
            "side": "back",
        }
        if after_ts is not None:
            params["after"] = str(after_ts)
        if before_ts is not None:
            params["before"] = str(before_ts)

        events: list[dict] = []
        offset = 0
        while True:
            params["offset"] = str(offset)
            payload = self._get("events", params)
            batch = payload.get("events") or []
            events.extend(batch)
            total = int(payload.get("total") or len(events))
            offset += len(batch)
            if not batch or offset >= total:
                break
        return events

    def place_back_offer(
        self,
        *,
        market_id: int,
        runner_id: int,
        odds: float,
        stake: float,
    ) -> dict:
        """
        Submit a back offer to Matchbook REST API.
        Live calls require HIBS_EXECUTION_LIVE=1; otherwise callers should dry-run via execution router.
        """
        if os.environ.get("HIBS_EXECUTION_LIVE", "").strip().lower() not in {"1", "true", "yes"}:
            raise NotImplementedError(
                "Matchbook live offers disabled — set HIBS_EXECUTION_LIVE=1 after paper validation."
            )
        self.login()
        url = f"{self._api_base}/offers"
        payload = {
            "offers": [
                {
                    "market-id": market_id,
                    "runner-id": runner_id,
                    "odds": odds,
                    "stake": stake,
                    "side": "back",
                }
            ]
        }
        resp = self._session.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        offers = data.get("offers") or []
        return offers[0] if offers else data


def build_matchbook_natural_key(event: dict) -> str:
    """Event → date_course_time key aligned with card settlement keys."""
    raw_course = _event_course_hint(event) or str(event.get("name") or "unknown")
    raw_utc = str(event.get("start") or "")
    race_date = matchbook_event_local_date(raw_utc) or raw_utc.split("T")[0]
    clean_time = normalize_matchbook_time_to_london(raw_utc)
    return generate_natural_key(race_date, raw_course, clean_time)


def _parse_event_start(start: str | None) -> tuple[str | None, str | None]:
    if not start:
        return None, None
    return matchbook_event_local_date(start), normalize_matchbook_time_to_london(start)


def _event_course_hint(event: dict) -> str:
    for tag in event.get("meta-tags") or []:
        ttype = str(tag.get("type") or "").upper()
        if ttype in {"COURSE", "VENUE", "LOCATION"}:
            return str(tag.get("name") or "")
    return str(event.get("name") or "")


def _match_event_to_race(event: dict, course: str | None, card_date: str | None, off_time: str | None) -> bool:
    from hibs_racing.entity.natural_key import courses_match, normalize_off_time

    ev_date, ev_time = _parse_event_start(event.get("start"))
    if card_date and ev_date and str(card_date) != ev_date:
        return False
    if off_time and ev_time:
        if normalize_off_time(off_time) != normalize_off_time(ev_time):
            return False
    if course:
        hint = _event_course_hint(event)
        if not courses_match(course, hint) and course.lower() not in (event.get("name") or "").lower():
            return False
    return True


def _select_win_market(markets: list[dict]) -> dict | None:
    for market in markets:
        name = str(market.get("name") or "").lower()
        mtype = str(market.get("market-type") or market.get("type") or "").lower()
        if "win" in name or "outright" in mtype or "single" in mtype:
            return market
    return markets[0] if markets else None


def _select_place_market(markets: list[dict]) -> dict | None:
    for market in markets:
        name = str(market.get("name") or "").lower()
        mtype = str(market.get("market-type") or market.get("type") or "").lower()
        if "place" in name or "place" in mtype:
            return market
    return None


def _runner_by_horse_name(market: dict, horse_name: str | None) -> dict | None:
    if not horse_name:
        return None
    for runner in market.get("runners") or []:
        if horse_names_match(horse_name, str(runner.get("name") or "")):
            return runner
    return None


def _best_back_price(runner: dict) -> float | None:
    prices = runner.get("prices") or []
    backs = [p for p in prices if str(p.get("side", "")).lower() == "back"]
    if not backs:
        return None
    decimals: list[float] = []
    for p in backs:
        val = p.get("decimal-odds") or p.get("odds")
        if val is not None:
            try:
                dec = float(val)
                if dec > 1.0:
                    decimals.append(dec)
            except (TypeError, ValueError):
                continue
    return max(decimals) if decimals else None


def _card_day_window(cards: pd.DataFrame) -> tuple[int | None, int | None]:
    """Card calendar dates are UK-local; Matchbook API timestamps are UTC."""
    if cards.empty or "card_date" not in cards.columns:
        return None, None
    dates = pd.to_datetime(cards["card_date"].astype(str), errors="coerce").dropna()
    if dates.empty:
        return None, None
    d_min = dates.min().date()
    d_max = dates.max().date()
    start = datetime.combine(d_min, dt_time.min, tzinfo=LONDON)
    end = datetime.combine(d_max, dt_time(23, 59, 59), tzinfo=LONDON)
    return int(start.timestamp()), int(end.timestamp())


def fetch_matchbook_odds(
    cards: pd.DataFrame,
    *,
    config_path: Path | None = None,
    client: MatchbookClient | None = None,
) -> tuple[pd.DataFrame, MatchbookFetchReport]:
    """Pull exchange back prices from Matchbook and align to card runners."""
    cfg = load_config(config_path)
    mb_cfg = cfg.get("matchbook", {})
    if not mb_cfg.get("enabled", True):
        return pd.DataFrame(), MatchbookFetchReport(errors=["matchbook disabled in config"])

    place_fraction = float(mb_cfg.get("default_place_fraction", 0.25))
    places = int(mb_cfg.get("default_places", 3))
    report = MatchbookFetchReport()

    try:
        client = client or MatchbookClient(config_path=config_path)
        after_ts, before_ts = _card_day_window(cards)
        events = client.fetch_horse_events(after_ts=after_ts, before_ts=before_ts)
        report.events_loaded = len(events)
    except Exception as exc:
        report.errors.append(str(exc))
        return pd.DataFrame(), report

    priced: list[dict] = []
    races = list(cards.groupby("race_id", sort=False))
    report.races_attempted = len(races)

    for race_id, race_df in races:
        first = race_df.iloc[0]
        course = first.get("course")
        card_date = str(first.get("card_date") or "")
        off_time = first.get("off_time")

        event = next(
            (ev for ev in events if _match_event_to_race(ev, course, card_date, off_time)),
            None,
        )
        if event is None:
            report.errors.append(f"{race_id}: no Matchbook event for {course} {off_time}")
            continue

        market = _select_win_market(event.get("markets") or [])
        if market is None:
            report.errors.append(f"{race_id}: no win market on event {event.get('id')}")
            continue

        place_market = _select_place_market(event.get("markets") or [])

        report.races_matched += 1
        runners = {str(r.get("name") or ""): r for r in market.get("runners") or []}

        for _, card_row in race_df.iterrows():
            horse = card_row.get("horse_name")
            mb_runner = None
            for name, runner in runners.items():
                if horse_names_match(horse, name):
                    mb_runner = runner
                    break
            if mb_runner is None:
                continue
            back = _best_back_price(mb_runner)
            if back is None:
                continue

            place_runner = _runner_by_horse_name(place_market, horse) if place_market else None
            place_back = _best_back_price(place_runner) if place_runner else None

            priced.append(
                {
                    "race_id": race_id,
                    "runner_id": card_row.get("runner_id"),
                    "horse_name": horse,
                    "win_decimal": back,
                    "place_decimal": place_back,
                    "best_book": "matchbook",
                    "matchbook_runner_id": mb_runner.get("id"),
                    "matchbook_market_id": market.get("id"),
                    "matchbook_place_runner_id": place_runner.get("id") if place_runner else None,
                    "matchbook_place_market_id": place_market.get("id") if place_market else None,
                    "matchbook_event_id": event.get("id"),
                    "race_natural_key": build_matchbook_natural_key(event),
                    "place_fraction": place_fraction,
                    "places": places,
                    "odds_source": "matchbook",
                }
            )

    report.runners_priced = len(priced)
    return pd.DataFrame(priced), report
