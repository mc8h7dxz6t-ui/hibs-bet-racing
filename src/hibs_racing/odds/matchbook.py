from __future__ import annotations

import json
import logging
import os
import re
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from datetime import time as dt_time
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from hibs_racing.config import load_config
from hibs_racing.entity.natural_key import courses_match, generate_natural_key, normalize_course, normalize_off_time
from hibs_racing.entity.timezone import LONDON, matchbook_event_local_date, normalize_matchbook_time_to_london
from hibs_racing.odds.exchange_quotes import exchange_spread_bps
from hibs_racing.odds.matching import horse_names_match

logger = logging.getLogger(__name__)

# Canonical slug → substrings to match in Matchbook event name / venue tags.
COURSE_ALIASES: dict[str, list[str]] = {
    "newton_abbot": ["newton abbot", "newton-abbot"],
    "stratford": ["stratford-on-avon", "stratford on avon", "stratford"],
    "fontwell": ["fontwell park", "fontwell"],
    "leopardstown": ["leopardstown (ire)", "leopardstown"],
    "newcastle": ["newcastle (aw)", "newcastle aw", "newcastle"],
    "kempton": ["kempton park", "kempton (aw)", "kempton"],
    "lingfield": ["lingfield park", "lingfield (aw)", "lingfield"],
    "wolverhampton": ["wolverhampton (aw)", "wolverhampton"],
    "southwell": ["southwell (aw)", "southwell"],
    "chelmsford": ["chelmsford city", "chelmsford (aw)", "chelmsford"],
    "brighton": ["brighton", "brighton & hove", "brighton and hove"],
    "great_yarmouth": ["great yarmouth", "yarmouth"],
    "hamilton": ["hamilton park", "hamilton"],
    "ayr": ["ayr", "ayr (scot)"],
    "perth": ["perth", "perth (scot)"],
    "downpatrick": ["downpatrick", "downpatrick (ni)"],
    "down_royal": ["down royal", "down royal (ni)"],
    "curragh": ["curragh", "curragh (ire)"],
    "galway": ["galway", "galway (ire)"],
    "punchestown": ["punchestown", "punchestown (ire)"],
    "naas": ["naas", "naas (ire)"],
    "tipperary": ["tipperary", "tipperary (ire)"],
    "wexford": ["wexford", "wexford (ire)"],
    "killarney": ["killarney", "killarney (ire)"],
    "roscommon": ["roscommon", "roscommon (ire)"],
    "sligo": ["sligo", "sligo (ire)"],
    "listowel": ["listowel", "listowel (ire)"],
    "bath": ["bath"],
    "salisbury": ["salisbury"],
    "goodwood": ["goodwood"],
    "york": ["york"],
    "doncaster": ["doncaster"],
    "ascot": ["ascot", "royal ascot"],
    "epsom": ["epsom", "epsom downs"],
    "sandown": ["sandown", "sandown park"],
    "kempton_park": ["kempton park", "kempton"],
}

_COURSE_SLUG_RE = re.compile(r"[^a-z0-9]+")

HORSE_RACING_SPORT_ID = 24735152712200
BPAPI_REST_BASE = "https://api.matchbook.com/bpapi/rest"
EDGE_REST_BASE = "https://api.matchbook.com/edge/rest"


@dataclass
class MatchbookFetchReport:
    races_attempted: int = 0
    races_matched: int = 0
    runners_priced: int = 0
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
            "events_loaded": self.events_loaded,
            "near_miss_count": self.near_miss_count,
            "exchange_venues_on_card_dates": self.exchange_venues_on_card_dates,
            "adjacent_day_fallback": self.adjacent_day_fallback,
            "date_slack_days": self.date_slack_days,
            "errors": self.errors,
        }


def _credentials() -> tuple[str, str]:
    user = (
        os.environ.get("MATCHBOOK_USERNAME", "").strip()
        or os.environ.get("MATCHBOOK_USER", "").strip()
    )
    password = os.environ.get("MATCHBOOK_PASSWORD", "").strip()
    if not user or not password:
        raise ValueError("Set MATCHBOOK_USER/USERNAME and MATCHBOOK_PASSWORD in .env")
    return user, password


def _api_base(cfg: dict) -> str:
    return os.environ.get("MATCHBOOK_API_BASE") or cfg.get("matchbook", {}).get(
        "api_base", EDGE_REST_BASE
    ).rstrip("/")


def _login_base(cfg: dict) -> str:
    return os.environ.get("MATCHBOOK_LOGIN_BASE") or cfg.get("matchbook", {}).get(
        "login_base", BPAPI_REST_BASE
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
        self._login_base = _login_base(cfg)
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

    def close(self) -> None:
        self._session.close()

    def __enter__(self) -> MatchbookClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def login(self, *, force: bool = False) -> str:
        if self._token and not force and (time.time() - self._token_at) < 5 * 3600:
            return self._token
        url = f"{self._login_base}/security/session"
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
        if resp.status_code == 429:
            from hibs_racing.matchbook_guard import record_rate_limit

            record_rate_limit(http_status=429, reason=path)
        resp.raise_for_status()
        raw = resp.content
        try:
            from inst_spine.webhook_wal import capture_before_parse

            capture_before_parse("matchbook", raw, source=path)
        except Exception:
            pass
        return json.loads(raw)

    def fetch_horse_events(
        self,
        *,
        after_ts: int | None = None,
        before_ts: int | None = None,
        include_prices: bool = True,
        tag_url_names: str | None = None,
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
        if tag_url_names:
            params["tag-url-names"] = tag_url_names
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


def _course_slug(course: str | None) -> str:
    if not course:
        return ""
    return normalize_course(course) or _COURSE_SLUG_RE.sub("_", str(course).lower().strip()).strip("_")


def _course_alias_tokens(course: str | None) -> list[str]:
    if not course:
        return []
    slug = _course_slug(course)
    tokens = list(COURSE_ALIASES.get(slug, []))
    base = str(course).lower().split("(")[0].strip()
    tokens.extend([base, slug.replace("_", " ")])
    tokens.append(slug)
    # de-dupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for t in tokens:
        t = t.strip().lower()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _exchange_course_strings(event: dict) -> list[str]:
    strings: list[str] = []
    for raw in (_event_course_hint(event), str(event.get("name") or "")):
        text = str(raw).lower().strip()
        if text and text not in strings:
            strings.append(text)
    return strings


def _venue_matches(card_course: str | None, event: dict) -> bool:
    if not card_course:
        return True
    aliases = _course_alias_tokens(card_course)
    for exch in _exchange_course_strings(event):
        if courses_match(card_course, exch):
            return True
        for alias in aliases:
            if alias in exch or exch in alias:
                return True
    return False


def _card_off_datetime(card_date: str | None, off_time: str | None) -> datetime | None:
    if not card_date or not off_time:
        return None
    try:
        d = date.fromisoformat(str(card_date)[:10])
    except ValueError:
        return None
    hm = normalize_off_time(off_time)
    try:
        hour, minute = (int(x) for x in hm.split(":", 1))
    except ValueError:
        return None
    return datetime.combine(d, dt_time(hour, minute), tzinfo=LONDON)


def _event_off_datetime(event: dict) -> datetime | None:
    start = event.get("start")
    if not start:
        return None
    text = str(start).strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("UTC"))
    return dt.astimezone(LONDON)


def _expand_card_dates(card_dates: set[str], slack_days: int) -> set[str]:
    """Include ±slack_days around each card calendar date (UK-local card_date labels)."""
    if slack_days <= 0:
        return set(card_dates)
    out = set(card_dates)
    for raw in card_dates:
        try:
            base = date.fromisoformat(str(raw)[:10])
        except ValueError:
            continue
        for delta in range(-slack_days, slack_days + 1):
            out.add((base + timedelta(days=delta)).isoformat())
    return out


def _dates_within_slack(card_date: str | None, ev_date: str | None, slack_days: int) -> bool:
    if not card_date or not ev_date:
        return True
    if str(card_date)[:10] == ev_date:
        return True
    if slack_days <= 0:
        return False
    try:
        cd = date.fromisoformat(str(card_date)[:10])
        ed = date.fromisoformat(str(ev_date)[:10])
    except ValueError:
        return False
    return abs((ed - cd).days) <= slack_days


def find_matching_exchange_event(
    exchange_events: list[dict],
    *,
    course: str | None,
    card_date: str | None,
    off_time: str | None,
    time_tolerance_sec: int = 120,
    near_miss_sec: int = 600,
    near_miss_counter: list[int] | None = None,
    date_slack_days: int = 0,
) -> dict | None:
    """
    Match card race → exchange event via venue aliases and ±time_tolerance_sec off-time.
    Logs NEAR_MISS when venue aligns but delta is within near_miss_sec (operational tuning).
    """
    card_dt = _card_off_datetime(card_date, off_time)
    best: tuple[float, dict] | None = None

    for event in exchange_events:
        ev_date = matchbook_event_local_date(event.get("start"))
        if not _dates_within_slack(card_date, ev_date, date_slack_days):
            continue
        if not _venue_matches(course, event):
            continue

        ev_dt = _event_off_datetime(event)
        if card_dt is None or ev_dt is None:
            if best is None:
                best = (0.0, event)
            continue

        delta = abs((card_dt - ev_dt).total_seconds())
        if delta <= time_tolerance_sec:
            if best is None or delta < best[0]:
                best = (delta, event)
        elif delta <= near_miss_sec:
            if near_miss_counter is not None:
                near_miss_counter[0] += 1
            logger.warning(
                "NEAR_MISS: Venue matched (%s), but time delta was %ss. Card: %s, Exchange: %s",
                course,
                int(delta),
                card_dt.isoformat(),
                ev_dt.isoformat(),
            )

    return best[1] if best else None


def _match_event_to_race(event: dict, course: str | None, card_date: str | None, off_time: str | None) -> bool:
    """Strict single-event check (used in tests); production uses find_matching_exchange_event."""
    return (
        find_matching_exchange_event(
            [event],
            course=course,
            card_date=card_date,
            off_time=off_time,
            time_tolerance_sec=0,
            near_miss_sec=0,
        )
        is not None
    )


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


def _price_decimal(price: dict) -> float | None:
    val = price.get("decimal-odds") or price.get("odds")
    if val is None:
        return None
    try:
        dec = float(val)
    except (TypeError, ValueError):
        return None
    return dec if dec > 1.0 else None


def _price_liquidity(price: dict) -> float | None:
    for key in ("available-amount", "available_amount", "liquidity", "stake"):
        val = price.get(key)
        if val is None:
            continue
        try:
            return float(val)
        except (TypeError, ValueError):
            continue
    return None


def _top_of_book(runner: dict, side: str) -> tuple[float | None, float | None]:
    """Best back (max decimal) or best lay (min decimal) with liquidity at that level."""
    prices = runner.get("prices") or []
    side_l = side.lower()
    matching = [p for p in prices if str(p.get("side", "")).lower() == side_l]
    if not matching:
        return None, None
    best_dec: float | None = None
    best_liq: float | None = None
    for p in matching:
        dec = _price_decimal(p)
        if dec is None:
            continue
        liq = _price_liquidity(p)
        if side_l == "back":
            if best_dec is None or dec > best_dec:
                best_dec, best_liq = dec, liq
        else:
            if best_dec is None or dec < best_dec:
                best_dec, best_liq = dec, liq
    return best_dec, best_liq


def _best_back_price(runner: dict) -> float | None:
    back, _ = _top_of_book(runner, "back")
    return back


def _is_gb_ire_event(event: dict) -> bool:
    """True when Matchbook tags an event as UK or Ireland racing."""
    for tag in event.get("meta-tags") or []:
        url = str(tag.get("url-name") or "").lower()
        name = str(tag.get("name") or "").lower()
        ttype = str(tag.get("type") or "").upper()
        if url in {"uk-ireland", "uk", "ireland"}:
            return True
        if ttype == "COUNTRY" and name in {"uk", "ireland"}:
            return True
    return False


def _filter_gb_ire_events(events: list[dict]) -> list[dict]:
    return [event for event in events if _is_gb_ire_event(event)]


def _events_on_card_dates(events: list[dict], card_dates: set[str]) -> list[dict]:
    matched: list[dict] = []
    for event in events:
        ev_date = matchbook_event_local_date(event.get("start"))
        if ev_date and ev_date in card_dates:
            matched.append(event)
    return matched


def _load_gb_ire_events_for_cards(
    client: MatchbookClient,
    cards: pd.DataFrame,
    *,
    mb_cfg: dict,
) -> tuple[list[dict], list[str], int]:
    """Fetch Matchbook horse events limited to GB/IRE and the card calendar date(s).

    Returns (events, sorted_card_dates, date_slack_days used for race matching).
    """
    card_dates = {str(d) for d in cards["card_date"].dropna().astype(str).unique()}
    tag_names = (mb_cfg.get("tag_url_names") or "").strip()
    tag_kw = {"tag_url_names": tag_names} if tag_names else {}
    slack_days = max(0, int(mb_cfg.get("date_slack_days", 1)))

    after_ts, before_ts = _card_day_window(cards)
    window_events = client.fetch_horse_events(after_ts=after_ts, before_ts=before_ts, **tag_kw)
    window_events = _filter_gb_ire_events(window_events)
    events = _events_on_card_dates(window_events, card_dates)
    date_slack_used = 0

    all_uk: list[dict] = []
    if not events:
        all_uk = _filter_gb_ire_events(client.fetch_horse_events(**tag_kw))
        events = _events_on_card_dates(all_uk, card_dates)

    if not events and slack_days > 0:
        expanded = _expand_card_dates(card_dates, slack_days)
        if not all_uk:
            all_uk = _filter_gb_ire_events(client.fetch_horse_events(**tag_kw))
        events = _events_on_card_dates(all_uk, expanded)
        if events:
            date_slack_used = slack_days

    if not events:
        if not all_uk:
            all_uk = _filter_gb_ire_events(client.fetch_horse_events(**tag_kw))
        available = sorted({d for d in (matchbook_event_local_date(e.get("start")) for e in all_uk) if d})
        courses = sorted(cards["course"].dropna().astype(str).unique().tolist())
        raise ValueError(
            "Matchbook has no GB/IRE markets for "
            f"{sorted(card_dates)} ({', '.join(courses)}). "
            f"API UK/IRE events available on: {available or 'none'}"
        )

    return events, sorted(card_dates), date_slack_used


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
    force: bool = False,
) -> tuple[pd.DataFrame, MatchbookFetchReport]:
    """Pull exchange back prices from Matchbook and align to card runners."""
    from hibs_racing.matchbook_guard import matchbook_traffic_allowed, record_poll_success

    if client is None and not matchbook_traffic_allowed(force=force):
        return pd.DataFrame(), MatchbookFetchReport(errors=["matchbook poll gated (rate/owner/trip)"])
    cfg = load_config(config_path)
    mb_cfg = cfg.get("matchbook", {})
    if not mb_cfg.get("enabled", True):
        return pd.DataFrame(), MatchbookFetchReport(errors=["matchbook disabled in config"])

    place_fraction = float(mb_cfg.get("default_place_fraction", 0.25))
    places = int(mb_cfg.get("default_places", 3))
    report = MatchbookFetchReport()

    owns_client = client is None
    client = client or MatchbookClient(config_path=config_path)
    date_slack_days = 0
    try:
        try:
            events, _card_dates, date_slack_days = _load_gb_ire_events_for_cards(client, cards, mb_cfg=mb_cfg)
            report.events_loaded = len(events)
            report.adjacent_day_fallback = date_slack_days > 0
            report.date_slack_days = date_slack_days
            venues: list[str] = []
            for ev in events:
                hint = _event_course_hint(ev)
                if hint and hint not in venues:
                    venues.append(hint)
            report.exchange_venues_on_card_dates = sorted(venues)[:30]
        except ValueError as exc:
            report.errors.append(str(exc))
            return pd.DataFrame(), report
        except Exception as exc:
            report.errors.append(str(exc))
            return pd.DataFrame(), report

        time_tol = int(mb_cfg.get("event_time_tolerance_sec", 120))
        near_miss_sec = int(mb_cfg.get("event_near_miss_sec", 600))
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
                back, back_liq = _top_of_book(mb_runner, "back")
                if back is None:
                    continue
                lay, lay_liq = _top_of_book(mb_runner, "lay")

                place_runner = _runner_by_horse_name(place_market, horse) if place_market else None
                place_back = _best_back_price(place_runner) if place_runner else None

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
        report.near_miss_count = near_miss_counter[0]
        if priced:
            record_poll_success()
        return pd.DataFrame(priced), report
    finally:
        if owns_client:
            client.close()
