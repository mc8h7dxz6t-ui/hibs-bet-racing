from __future__ import annotations

import os
import re
import sys
import time
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from hibs_racing.cards.window import off_minutes

ROOT = Path(__file__).resolve().parents[3]
RPSCRAPE_SCRIPTS = ROOT / "vendor" / "rpscrape" / "scripts"


def _rp_auth_ok() -> bool:
    return bool(os.environ.get("EMAIL", "").strip() and os.environ.get("ACCESS_TOKEN", "").strip())


def _norm_course(name: object) -> str:
    return re.sub(r"\s+", " ", str(name or "").strip().lower())


def _norm_off_key(off_time: object) -> int:
    return off_minutes(off_time)


def _client():
    if str(RPSCRAPE_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(RPSCRAPE_SCRIPTS))
    from utils.network import NetworkClient  # type: ignore[import-not-found]

    return NetworkClient(
        email=os.environ.get("EMAIL"),
        access_token=os.environ.get("ACCESS_TOKEN"),
    )


def _off_from_rp_race(race: dict[str, Any]) -> int:
    sched = race.get("startScheduledDatetime") or {}
    local = str(sched.get("local") or sched.get("utc") or "")
    m = re.search(r"T(\d{2}):(\d{2})", local)
    if m:
        return int(m.group(1)) * 60 + int(m.group(2))
    return _norm_off_key(race.get("time") or race.get("startTime"))


@lru_cache(maxsize=8)
def _meetings_for_date(card_date: str) -> tuple[dict[tuple[str, int], dict[str, Any]], bool]:
    """Index RP meetings by (course, off_minutes) for a card date."""
    if not _rp_auth_ok():
        return {}, False
    try:
        client = _client()
        status, resp = client.get(f"https://www.racingpost.com/api/racing/meetings/?date={card_date}")
        if status != 200:
            return {}, False
        index: dict[tuple[str, int], dict[str, Any]] = {}
        for meeting in resp.json().get("meetings") or []:
            course = _norm_course(meeting.get("courseKey") or meeting.get("venueName"))
            cid = meeting.get("venueUid")
            ck = meeting.get("courseKey")
            for race in meeting.get("races") or []:
                off = _off_from_rp_race(race)
                if not course or off >= 9999:
                    continue
                index[(course, off)] = {
                    "rp_race_id": str(race.get("raceId") or ""),
                    "course_id": cid,
                    "course_key": ck,
                    "card_date": card_date,
                    "race_title": race.get("raceTitle"),
                }
        return index, True
    except Exception:
        return {}, False


def extract_rp_verdict(
    tabs_content: dict[str, Any] | None,
    runners_page: list[dict[str, Any]] | None,
    race_details: dict[str, Any] | None,
) -> str | None:
    """Build RP verdict text from race page JSON (official tab or best available fallback)."""
    tabs_content = tabs_content or {}
    raw = tabs_content.get("verdict")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    if isinstance(raw, dict):
        for key in ("text", "verdict", "body", "content", "html"):
            val = raw.get(key)
            if isinstance(val, str) and val.strip():
                return _strip_html(val.strip())

    runners_page = runners_page or []
    tipped = sorted(
        runners_page,
        key=lambda r: int(r.get("numberOfTips") or 0),
        reverse=True,
    )
    if tipped and int(tipped[0].get("numberOfTips") or 0) > 0:
        top = tipped[0]
        spot = (top.get("spotlight") or top.get("diomed") or "").strip()
        if spot:
            name = (top.get("horseName") or top.get("name") or "").strip()
            return f"{name} — {spot}" if name else spot

    race_details = race_details or {}
    forecast = race_details.get("bettingForecast") or []
    if forecast:
        parts: list[str] = []
        for item in forecast[:4]:
            horses = item.get("horses") or []
            names = ", ".join(str(h.get("horseName") or "").strip() for h in horses if h.get("horseName"))
            odds = item.get("oddsDesc") or item.get("oddsValue")
            if names and odds:
                parts.append(f"{odds} {names}")
        if parts:
            return "RP forecast: " + "; ".join(parts)
    return None


def _strip_html(text: str) -> str:
    return re.sub(r"<[^>]+>", " ", text).replace("&nbsp;", " ").strip()


def _lookup_race_meta(index: dict[tuple[str, int], dict[str, Any]], course: str, off_time: object) -> dict[str, Any] | None:
    course_key = _norm_course(course)
    off_key = _norm_off_key(off_time)
    candidates = [off_key]
    if off_key < 12 * 60:
        candidates.append(off_key + 12 * 60)
    for off in candidates:
        meta = index.get((course_key, off))
        if meta:
            return meta
    if course:
        needle = course_key
        for off in candidates:
            for (c, idx_off), row in index.items():
                if idx_off == off and (needle in c or c in needle):
                    return row
    return None


def fetch_rp_verdict_for_race(
    *,
    card_date: str,
    course: str,
    off_time: object,
    rp_race_id: str | None = None,
    course_id: object | None = None,
    course_key: str | None = None,
) -> str | None:
    if not _rp_auth_ok():
        return None

    meta: dict[str, Any] | None = None
    if rp_race_id and course_id and course_key:
        meta = {
            "rp_race_id": str(rp_race_id),
            "course_id": course_id,
            "course_key": course_key,
            "card_date": card_date,
        }
    else:
        index, ok = _meetings_for_date(str(card_date)[:10])
        if not ok:
            return None
        meta = _lookup_race_meta(index, course, off_time)
    if not meta or not meta.get("rp_race_id"):
        return None

    url = (
        f"https://www.racingpost.com/racecards/{meta['course_id']}/"
        f"{meta['course_key']}/{meta['card_date']}/{meta['rp_race_id']}/"
    )
    try:
        from lxml import html
        from orjson import loads

        client = _client()
        status, resp = client.get(url)
        if status != 200:
            return None
        doc = html.fromstring(resp.content)
        node = doc.get_element_by_id("__NEXT_DATA__")
        data = loads(node.text_content())
        page = data["props"]["pageProps"]["initialState"]["racePage"]["data"]
        return extract_rp_verdict(
            page.get("tabsContent"),
            page.get("runners"),
            page.get("raceDetails"),
        )
    except Exception:
        return None


def enrich_cards_with_rp_verdicts(
    cards: pd.DataFrame,
    *,
    sleep_sec: float = 0.0,
    max_workers: int = 1,
) -> pd.DataFrame:
    """Attach race-level RP verdict to each runner row (when credentials are set)."""
    if cards.empty:
        return cards
    out = cards.copy()
    if "rp_verdict" not in out.columns:
        out["rp_verdict"] = None

    if not _rp_auth_ok():
        return out

    keys = (
        out.groupby(["card_date", "course", "off_time"], dropna=False)
        .size()
        .reset_index()[["card_date", "course", "off_time"]]
    )
    records = keys.to_dict(orient="records")
    verdict_map: dict[tuple[str, str, str], str | None] = {}

    def _fetch_one(rec: dict) -> tuple[tuple[str, str, str], str | None]:
        card_date = str(rec["card_date"])[:10]
        course = str(rec["course"] or "")
        off_time = rec["off_time"]
        key = (card_date, course, str(off_time or ""))
        verdict = fetch_rp_verdict_for_race(
            card_date=card_date,
            course=course,
            off_time=off_time,
        )
        if sleep_sec:
            time.sleep(sleep_sec)
        return key, verdict

    workers = max(1, min(int(max_workers), len(records) or 1))
    if workers > 1 and len(records) > 1:
        from concurrent.futures import ThreadPoolExecutor, as_completed

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_fetch_one, rec) for rec in records]
            for fut in as_completed(futures):
                key, verdict = fut.result()
                verdict_map[key] = verdict
    else:
        for rec in records:
            key, verdict = _fetch_one(rec)
            verdict_map[key] = verdict

    def _lookup(row: pd.Series) -> object:
        existing = row.get("rp_verdict")
        if isinstance(existing, str) and existing.strip():
            return existing.strip()
        key = (str(row.get("card_date"))[:10], str(row.get("course") or ""), str(row.get("off_time") or ""))
        return verdict_map.get(key)

    out["rp_verdict"] = out.apply(_lookup, axis=1)
    return out


def race_verdict_from_runners(race_df: pd.DataFrame) -> str | None:
    """Fallback when live RP fetch unavailable — top model runner's RP comment."""
    if race_df.empty:
        return None
    if "rp_verdict" in race_df.columns:
        for val in race_df["rp_verdict"].dropna().astype(str):
            if val.strip():
                return val.strip()
    if "card_comment" not in race_df.columns:
        return None
    frame = race_df.copy()
    frame["_comment"] = frame["card_comment"].fillna("").astype(str).str.strip()
    frame = frame[frame["_comment"] != ""]
    if frame.empty:
        return None
    if "model_place_prob" in frame.columns:
        frame = frame.sort_values("model_place_prob", ascending=False, na_position="last")
    row = frame.iloc[0]
    name = str(row.get("horse_name") or "").strip()
    comment = str(row.get("_comment") or "").strip()
    if name and comment:
        return f"{name} — {comment}"
    return comment or None
