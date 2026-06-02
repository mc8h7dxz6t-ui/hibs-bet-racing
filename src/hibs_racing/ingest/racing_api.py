from __future__ import annotations

import os
import time

import pandas as pd
import requests

from hibs_racing.ingest.rate_limit import pause_sec, polite_sleep, racing_api_pause
from hibs_racing.ingest.scrape import _load_env

ENDPOINTS = {
    "free": "/racecards/free",
    "basic": "/racecards/basic",
    "standard": "/racecards/standard",
}


def _api_day(day: int | None) -> str:
    """Map CLI day index to Racing API day query (today / tomorrow)."""
    if day is None or day <= 1:
        return "today"
    if day == 2:
        return "tomorrow"
    raise ValueError("Racing API free/basic plans only support day 1 (today) or 2 (tomorrow)")


def _race_id(race: dict, *, fallback_date: str) -> str:
    rid = race.get("race_id") or race.get("id")
    if rid:
        return str(rid)
    course = race.get("course") or "course"
    off = race.get("off_time") or race.get("off_dt") or "00:00"
    return f"{fallback_date}_{course}_{off}".replace(" ", "_").lower()


def parse_racing_api_payload(payload: dict, *, region: str, card_date: str | None = None) -> pd.DataFrame:
    """Flatten The Racing API racecards JSON → runner rows."""
    rows: list[dict] = []
    for race in payload.get("racecards") or []:
        if race.get("is_abandoned"):
            continue
        race_date = str(race.get("date") or card_date or "")
        race_id = _race_id(race, fallback_date=race_date)
        runners = race.get("runners") or []
        for runner in runners:
            if runner.get("non_runner") or runner.get("reserve"):
                continue
            horse = runner.get("horse") or runner.get("horse_name") or ""
            rows.append(
                {
                    "race_id": race_id,
                    "card_date": race_date,
                    "off_time": race.get("off_time") or race.get("off_dt"),
                    "course": race.get("course"),
                    "region": (race.get("region") or region).upper(),
                    "race_name": race.get("race_name"),
                    "race_type": race.get("type"),
                    "race_class": str(race.get("race_class") or race.get("class") or ""),
                    "going": race.get("going"),
                    "distance_f": _float_or_none(race.get("distance_f") or race.get("dist_f")),
                    "field_size": int(race.get("field_size") or len(runners) or 0),
                    "horse_id": str(runner.get("horse_id") or horse),
                    "horse_name": horse,
                    "draw": _int_or_none(runner.get("draw")),
                    "official_rating": _int_or_none(runner.get("ofr") or runner.get("or")),
                    "rpr": _int_or_none(runner.get("rpr")),
                    "jockey": runner.get("jockey"),
                    "trainer": runner.get("trainer"),
                    "days_since_last_run": _int_or_none(runner.get("last_run")),
                    "card_comment": runner.get("comment") or runner.get("spotlight") or "",
                    "win_decimal": _float_or_none(
                        runner.get("odds_decimal") or runner.get("sp_dec") or runner.get("price")
                    ),
                }
            )
    if not rows:
        raise ValueError("Racing API returned no runners for this query.")
    frame = pd.DataFrame(rows)
    frame["runner_id"] = (
        frame["race_id"].astype(str)
        + ":"
        + frame["horse_name"].str.lower().str.replace(r"\s+", "_", regex=True)
    )
    return frame


def _int_or_none(value: object) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(float(str(value)))
    except (TypeError, ValueError):
        return None


def _float_or_none(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _request_racecards(
    *,
    day: str,
    region: str,
    plan: str,
    user: str,
    password: str,
    base: str,
) -> dict:
    endpoint = ENDPOINTS.get(plan, ENDPOINTS["free"])
    url = f"{base.rstrip('/')}{endpoint}"
    params: dict[str, object] = {"day": day, "region_codes": [region.lower()]}
    retries = max(1, int(pause_sec("racing_api_429_retries")))
    pause = pause_sec("racing_api_429_pause_sec")
    last_resp: requests.Response | None = None
    for attempt in range(retries):
        resp = requests.get(url, params=params, auth=(user, password), timeout=30)
        last_resp = resp
        if resp.status_code != 429:
            break
        if attempt + 1 < retries:
            time.sleep(pause * (attempt + 1))
    resp = last_resp
    assert resp is not None
    if resp.status_code == 401:
        raise RuntimeError(
            "Racing API 401 — check RACING_API_USERNAME and RACING_API_PASSWORD in .env "
            "(Dashboard → My Account on theracingapi.com)."
        )
    if resp.status_code == 403:
        raise RuntimeError(
            f"Racing API 403 — plan '{plan}' may not include {endpoint}. "
            "Set RACING_API_PLAN=free (default) or upgrade."
        )
    resp.raise_for_status()
    return resp.json()


def fetch_racing_api_racecards(
    *,
    day: int | None = 1,
    days: int | None = None,
    region: str = "gb",
) -> pd.DataFrame:
    """
    The Racing API racecards.

    Free plan: GET /v1/racecards/free (today + tomorrow, basic runner fields, no comments).
    Set RACING_API_USERNAME + RACING_API_PASSWORD from theracingapi.com → My Account.
    """
    env = _load_env() or os.environ
    user = env.get("RACING_API_USERNAME") or env.get("RACING_API_USER")
    password = env.get("RACING_API_PASSWORD") or env.get("RACING_API_KEY")
    if not user or not password:
        raise RuntimeError(
            "Racing API not configured. Add to ~/hibs-racing/.env:\n"
            "  RACING_API_USERNAME=...\n"
            "  RACING_API_PASSWORD=...\n"
            "Keys are under My Account at https://www.theracingapi.com"
        )

    plan = (env.get("RACING_API_PLAN") or "free").lower()
    base = env.get("RACING_API_BASE", "https://api.theracingapi.com/v1")

    if days is not None and day not in (None, 1):
        raise ValueError("Use either day= or days= with Racing API, not both")

    api_days: list[str]
    if days is not None:
        api_days = ["today"] if days <= 1 else ["today", "tomorrow"][:days]
    else:
        api_days = [_api_day(day)]

    frames: list[pd.DataFrame] = []
    api_pause = racing_api_pause()
    for i, api_day in enumerate(api_days):
        if i > 0:
            polite_sleep("racing_api_pause_sec")
        payload = _request_racecards(
            day=api_day,
            region=region,
            plan=plan,
            user=user,
            password=password,
            base=base,
        )
        try:
            frames.append(parse_racing_api_payload(payload, region=region))
        except ValueError as exc:
            # Tomorrow often has no IRE card; skip empty day when fetching today+tomorrow.
            if str(exc) != "Racing API returned no runners for this query." or len(api_days) == 1:
                raise
            continue

    if not frames:
        raise ValueError("Racing API returned no runners for this query.")
    if len(frames) == 1:
        return frames[0]
    return pd.concat(frames, ignore_index=True)
