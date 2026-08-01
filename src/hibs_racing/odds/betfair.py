"""Betfair Exchange odds — delayed app key (free personal tier) with course/horse normalization."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.config import load_config
from hibs_racing.entity.natural_key import generate_natural_key
from hibs_racing.entity.timezone import LONDON, matchbook_event_local_date, normalize_matchbook_time_to_london
from hibs_racing.odds.course_aliases import resolve_course_aliases
from hibs_racing.odds.exchange_quotes import exchange_spread_bps
from hibs_racing.odds.matchbook import (
    _card_day_window,
    _expand_card_dates,
    _runner_by_horse_name,
    _select_place_market,
    _select_win_market,
    _top_of_book,
    find_matching_exchange_event,
)
from hibs_racing.odds.matching import horse_names_match

logger = logging.getLogger(__name__)

HORSE_RACING_EVENT_TYPE_ID = "7"
IDENTITY_LOGIN_URL = "https://identitysso.betfair.com/api/login"
BETTING_API_BASE = "https://api.betfair.com/exchange/betting/rest/v1.0"


@dataclass
class BetfairFetchReport:
    races_attempted: int = 0
    races_matched: int = 0
    runners_priced: int = 0
    runners_skipped_no_odds: int = 0
    events_loaded: int = 0
    near_miss_count: int = 0
    exchange_venues_on_card_dates: list[str] = field(default_factory=list)
    adjacent_day_fallback: bool = False
    date_slack_days: int = 0
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "races_attempted": self.races_attempted,
            "races_matched": self.races_matched,
            "runners_priced": self.runners_priced,
            "runners_skipped_no_odds": self.runners_skipped_no_odds,
            "events_loaded": self.events_loaded,
            "near_miss_count": self.near_miss_count,
            "exchange_venues_on_card_dates": self.exchange_venues_on_card_dates,
            "adjacent_day_fallback": self.adjacent_day_fallback,
            "date_slack_days": self.date_slack_days,
            "errors": self.errors,
        }


def betfair_credentials() -> tuple[str, str, str]:
    app_key = os.environ.get("BETFAIR_APP_KEY", "").strip()
    username = os.environ.get("BETFAIR_USERNAME", "").strip()
    password = os.environ.get("BETFAIR_PASSWORD", "").strip()
    if not app_key or not username or not password:
        raise ValueError("Set BETFAIR_APP_KEY, BETFAIR_USERNAME, and BETFAIR_PASSWORD in .env")
    return app_key, username, password


def betfair_odds_configured() -> bool:
    try:
        betfair_credentials()
        return True
    except ValueError:
        return False


class BetfairClient:
    """Betfair Exchange REST client (delayed personal app key — no £300 activation)."""

    def __init__(
        self,
        *,
        app_key: str | None = None,
        username: str | None = None,
        password: str | None = None,
        api_base: str | None = None,
        login_url: str | None = None,
        config_path: Path | None = None,
    ) -> None:
        try:
            import requests
        except ImportError as exc:
            raise ImportError('Install api extra: pip install -e ".[api]"') from exc

        cfg = load_config(config_path)
        bf = cfg.get("betfair", {})
        if app_key and username and password:
            self._app_key, self._username, self._password = app_key, username, password
        else:
            self._app_key, self._username, self._password = betfair_credentials()
        self._api_base = (api_base or bf.get("api_base") or BETTING_API_BASE).rstrip("/")
        self._login_url = login_url or bf.get("login_url") or IDENTITY_LOGIN_URL
        self._session = requests.Session()
        self._session.headers.update(
            {
                "X-Application": self._app_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )
        self._token: str | None = None
        self._token_at: float = 0.0

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> BetfairClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def login(self, *, force: bool = False) -> str:
        if self._token and not force and (time.time() - self._token_at) < 4 * 3600:
            return self._token
        resp = self._session.post(
            self._login_url,
            data={"username": self._username, "password": self._password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        resp.raise_for_status()
        payload = resp.json()
        token = payload.get("token") or payload.get("sessionToken")
        status = str(payload.get("status") or payload.get("loginStatus") or "").upper()
        if not token or status not in {"SUCCESS", ""}:
            raise ValueError(f"Betfair login failed: {payload}")
        self._token = str(token)
        self._token_at = time.time()
        self._session.headers["X-Authentication"] = self._token
        return self._token

    def _post(self, endpoint: str, body: dict) -> Any:
        self.login()
        url = f"{self._api_base}/{endpoint.lstrip('/')}"
        resp = self._session.post(url, json=body, timeout=45)
        resp.raise_for_status()
        raw = resp.content
        try:
            from inst_spine.webhook_wal import capture_before_parse

            capture_before_parse("betfair", raw, source=endpoint)
        except Exception:
            pass
        return resp.json()

    def list_market_catalogue(
        self,
        *,
        after: str | None = None,
        before: str | None = None,
        countries: list[str] | None = None,
        market_types: list[str] | None = None,
        max_results: int = 200,
    ) -> list[dict]:
        filt: dict[str, Any] = {
            "eventTypeIds": [HORSE_RACING_EVENT_TYPE_ID],
            "marketCountries": countries or ["GB", "IE"],
            "marketTypeCodes": market_types or ["WIN"],
        }
        if after or before:
            filt["marketStartTime"] = {}
            if after:
                filt["marketStartTime"]["from"] = after
            if before:
                filt["marketStartTime"]["to"] = before
        payload = {
            "filter": filt,
            "marketProjection": ["EVENT", "RUNNER_DESCRIPTION", "MARKET_START_TIME"],
            "maxResults": str(max_results),
        }
        result = self._post("listMarketCatalogue/", payload)
        return list(result or [])

    def list_market_book(self, market_ids: list[str]) -> list[dict]:
        if not market_ids:
            return []
        payload = {
            "marketIds": market_ids,
            "priceProjection": {"priceData": ["EX_BEST_OFFERS"]},
            "orderProjection": "EXECUTABLE",
            "matchProjection": "ROLLED_UP_BY_PRICE",
        }
        result = self._post("listMarketBook/", payload)
        return list(result or [])


def build_betfair_natural_key(event: dict) -> str:
    venue = str((event.get("event") or {}).get("venue") or event.get("venue") or "unknown")
    raw_utc = str((event.get("event") or {}).get("openDate") or event.get("start") or "")
    race_date = matchbook_event_local_date(raw_utc) or raw_utc.split("T")[0]
    clean_time = normalize_matchbook_time_to_london(raw_utc)
    return generate_natural_key(race_date, venue, clean_time)


def _catalogue_event_hint(cat: dict) -> str:
    event = cat.get("event") or {}
    return str(event.get("venue") or event.get("name") or "")


def _catalogue_to_exchange_event(catalogues: list[dict]) -> dict[str, dict]:
    """Group Betfair catalogue rows by event id into Matchbook-shaped event dicts."""
    by_event: dict[str, dict] = {}
    for cat in catalogues:
        event = cat.get("event") or {}
        event_id = str(event.get("id") or cat.get("eventId") or "")
        if not event_id:
            continue
        venue = str(event.get("venue") or "")
        open_date = event.get("openDate")
        if event_id not in by_event:
            by_event[event_id] = {
                "id": event_id,
                "start": open_date,
                "name": event.get("name") or venue,
                "meta-tags": [{"type": "VENUE", "name": venue}],
                "markets": [],
                "_catalogue": [],
            }
        market = _catalogue_market_dict(cat)
        by_event[event_id]["markets"].append(market)
        by_event[event_id]["_catalogue"].append(cat)
    return by_event


def _catalogue_market_dict(cat: dict) -> dict:
    runners = []
    for runner in cat.get("runners") or []:
        runners.append(
            {
                "id": runner.get("selectionId"),
                "name": runner.get("runnerName") or runner.get("name"),
                "prices": [],
                "status": str(runner.get("status") or "ACTIVE"),
            }
        )
    mtype = str(cat.get("marketName") or cat.get("description", {}).get("marketType") or "")
    return {
        "id": cat.get("marketId"),
        "name": mtype or "Win",
        "market-type": "place" if "place" in mtype.lower() else "outright",
        "runners": runners,
    }


def _merge_market_books(events: dict[str, dict], books: list[dict]) -> None:
    book_by_id = {str(b.get("marketId")): b for b in books}
    for event in events.values():
        for market in event.get("markets") or []:
            book = book_by_id.get(str(market.get("id")))
            if not book:
                continue
            status_by_sel = {
                str(r.get("selectionId")): str(r.get("status") or "ACTIVE")
                for r in book.get("runners") or []
            }
            for runner in market.get("runners") or []:
                sel = str(runner.get("id"))
                runner["status"] = status_by_sel.get(sel, runner.get("status", "ACTIVE"))
                book_runner = next(
                    (r for r in book.get("runners") or [] if str(r.get("selectionId")) == sel),
                    None,
                )
                if not book_runner:
                    continue
                ex = book_runner.get("ex") or {}
                prices: list[dict] = []
                for level in ex.get("availableToBack") or []:
                    try:
                        dec = float(level.get("price"))
                        size = float(level.get("size", 0))
                    except (TypeError, ValueError):
                        continue
                    if dec > 1.0:
                        prices.append({"side": "back", "decimal-odds": dec, "available-amount": size})
                for level in ex.get("availableToLay") or []:
                    try:
                        dec = float(level.get("price"))
                        size = float(level.get("size", 0))
                    except (TypeError, ValueError):
                        continue
                    if dec > 1.0:
                        prices.append({"side": "lay", "decimal-odds": dec, "available-amount": size})
                runner["prices"] = prices


def _runner_has_odds(runner: dict) -> bool:
    status = str(runner.get("status") or "ACTIVE").upper()
    if status in {"REMOVED", "NON_RUNNER", "NONRUNNER"}:
        return False
    back, _ = _top_of_book(runner, "back")
    return back is not None and back > 1.0


def _iso_window(after_ts: int | None, before_ts: int | None) -> tuple[str | None, str | None]:
    if after_ts is None and before_ts is None:
        return None, None
    after = datetime.fromtimestamp(after_ts, tz=LONDON).isoformat() if after_ts is not None else None
    before = datetime.fromtimestamp(before_ts, tz=LONDON).isoformat() if before_ts is not None else None
    return after, before


def _events_on_card_dates(events: dict[str, dict], card_dates: set[str]) -> list[dict]:
    matched: list[dict] = []
    for event in events.values():
        ev_date = matchbook_event_local_date(event.get("start"))
        if ev_date and ev_date in card_dates:
            matched.append(event)
    return matched


def _load_gb_ire_events_for_cards(
    client: BetfairClient,
    cards: pd.DataFrame,
    *,
    bf_cfg: dict,
) -> tuple[list[dict], list[str], int]:
    card_dates = {str(d) for d in cards["card_date"].dropna().astype(str).unique()}
    slack_days = max(0, int(bf_cfg.get("date_slack_days", 1)))
    countries = list(bf_cfg.get("market_countries") or ["GB", "IE"])

    after_ts, before_ts = _card_day_window(cards)
    after_iso, before_iso = _iso_window(after_ts, before_ts)
    win_catalogues = client.list_market_catalogue(
        after=after_iso, before=before_iso, countries=countries, market_types=["WIN"]
    )
    place_catalogues = client.list_market_catalogue(
        after=after_iso, before=before_iso, countries=countries, market_types=["PLACE"]
    )
    all_catalogues = win_catalogues + place_catalogues
    events_map = _catalogue_to_exchange_event(all_catalogues)
    events = _events_on_card_dates(events_map, card_dates)
    date_slack_used = 0

    if not events and slack_days > 0:
        expanded = _expand_card_dates(card_dates, slack_days)
        events = _events_on_card_dates(events_map, expanded)
        if events:
            date_slack_used = slack_days

    if not events:
        available = sorted(
            {d for d in (matchbook_event_local_date(e.get("start")) for e in events_map.values()) if d}
        )
        courses = sorted(cards["course"].dropna().astype(str).unique().tolist())
        raise ValueError(
            "Betfair has no GB/IRE markets for "
            f"{sorted(card_dates)} ({', '.join(courses)}). "
            f"API events available on: {available or 'none'}"
        )

    market_ids = []
    for event in events:
        for market in event.get("markets") or []:
            mid = market.get("id")
            if mid:
                market_ids.append(str(mid))
    for chunk_start in range(0, len(market_ids), 40):
        books = client.list_market_book(market_ids[chunk_start : chunk_start + 40])
        _merge_market_books(events_map, books)

    return events, sorted(card_dates), date_slack_used


def fetch_betfair_odds(
    cards: pd.DataFrame,
    *,
    config_path: Path | None = None,
    client: BetfairClient | None = None,
) -> tuple[pd.DataFrame, BetfairFetchReport]:
    """Pull exchange back/lay prices from Betfair and align to card runners."""
    cfg = load_config(config_path)
    resolve_course_aliases(cfg)
    bf_cfg = cfg.get("betfair", {})
    if not bf_cfg.get("enabled", True):
        return pd.DataFrame(), BetfairFetchReport(errors=["betfair disabled in config"])

    place_fraction = float(bf_cfg.get("default_place_fraction", 0.25))
    places = int(bf_cfg.get("default_places", 3))
    report = BetfairFetchReport()

    owns_client = client is None
    client = client or BetfairClient(config_path=config_path)
    date_slack_days = 0
    try:
        try:
            events, _card_dates, date_slack_days = _load_gb_ire_events_for_cards(
                client, cards, bf_cfg=bf_cfg
            )
            report.events_loaded = len(events)
            report.adjacent_day_fallback = date_slack_days > 0
            report.date_slack_days = date_slack_days
            venues: list[str] = []
            for ev in events:
                hint = _catalogue_event_hint({"event": {"venue": (ev.get("meta-tags") or [{}])[0].get("name")}})
                if hint and hint not in venues:
                    venues.append(hint)
            report.exchange_venues_on_card_dates = sorted(venues)[:30]
        except ValueError as exc:
            report.errors.append(str(exc))
            return pd.DataFrame(), report
        except Exception as exc:
            report.errors.append(str(exc))
            return pd.DataFrame(), report

        time_tol = int(bf_cfg.get("event_time_tolerance_sec", 120))
        near_miss_sec = int(bf_cfg.get("event_near_miss_sec", 600))
        near_miss_counter = [0]

        priced: list[dict] = []
        races = list(cards.groupby("race_id", sort=False))
        report.races_attempted = len(races)

        for race_id, race_df in races:
            first = race_df.iloc[0]
            course = first.get("course")
            card_date = str(first.get("card_date") or "")
            off_time = first.get("off_time")

            event = find_matching_exchange_event(
                events,
                course=course,
                card_date=card_date,
                off_time=off_time,
                time_tolerance_sec=time_tol,
                near_miss_sec=near_miss_sec,
                near_miss_counter=near_miss_counter,
                date_slack_days=date_slack_days,
            )
            if event is None:
                if len(report.errors) < 5:
                    report.errors.append(f"{race_id}: no Betfair event for {course} {off_time}")
                continue

            market = _select_win_market(event.get("markets") or [])
            if market is None:
                report.errors.append(f"{race_id}: no win market on event {event.get('id')}")
                continue

            place_market = _select_place_market(event.get("markets") or [])
            report.races_matched += 1

            for _, card_row in race_df.iterrows():
                horse = card_row.get("horse_name")
                bf_runner = None
                for runner in market.get("runners") or []:
                    if horse_names_match(horse, str(runner.get("name") or "")):
                        bf_runner = runner
                        break
                if bf_runner is None:
                    continue
                if not _runner_has_odds(bf_runner):
                    report.runners_skipped_no_odds += 1
                    continue

                back, back_liq = _top_of_book(bf_runner, "back")
                if back is None:
                    report.runners_skipped_no_odds += 1
                    continue
                lay, lay_liq = _top_of_book(bf_runner, "lay")

                place_runner = _runner_by_horse_name(place_market, horse) if place_market else None
                place_back = None
                if place_runner and _runner_has_odds(place_runner):
                    place_back, _ = _top_of_book(place_runner, "back")

                priced.append(
                    {
                        "race_id": race_id,
                        "runner_id": card_row.get("runner_id"),
                        "card_date": card_date,
                        "horse_name": horse,
                        "win_decimal": back,
                        "back_price": back,
                        "back_liquidity": back_liq,
                        "lay_price": lay,
                        "lay_liquidity": lay_liq,
                        "exchange_spread_bps": exchange_spread_bps(back, lay),
                        "place_decimal": place_back,
                        "best_book": "betfair",
                        "betfair_selection_id": bf_runner.get("id"),
                        "betfair_market_id": market.get("id"),
                        "betfair_place_market_id": place_market.get("id") if place_market else None,
                        "betfair_event_id": event.get("id"),
                        "race_natural_key": build_betfair_natural_key(
                            {"event": {"venue": course, "openDate": event.get("start")}}
                        ),
                        "place_fraction": place_fraction,
                        "places": places,
                        "odds_source": "betfair",
                    }
                )

        report.runners_priced = len(priced)
        report.near_miss_count = near_miss_counter[0]
        return pd.DataFrame(priced), report
    finally:
        if owns_client:
            client.close()
