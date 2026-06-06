"""API-only historical RP racecards — bypasses __NEXT_DATA__ HTML scrape."""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path
from typing import Any

from hibs_racing.config import ROOT
from hibs_racing.ingest.racecards import RPSCRAPE_RACECARDS, _sync_rpscrape_dotenv

VENDOR_SCRIPTS = ROOT / "vendor" / "rpscrape" / "scripts"


def _import_vendor():
    if str(VENDOR_SCRIPTS) not in sys.path:
        sys.path.insert(0, str(VENDOR_SCRIPTS))
    from racecards import get_meetings, load_field_config, parse_runners  # noqa: WPS433
    from utils.network import NetworkClient  # noqa: WPS433
    from utils.stats import Stats  # noqa: WPS433

    return get_meetings, load_field_config, parse_runners, NetworkClient, Stats


def _off_time(race: dict[str, Any]) -> str:
    sched = race.get("startScheduledDatetime") or {}
    local = str(sched.get("local") or sched.get("utc") or "")
    if "T" in local:
        return local.split("T")[1][:5]
    return "00:00"


def _distance_f(race: dict[str, Any], runners_json: list[dict[str, Any]]) -> float | None:
    dist = race.get("distance") or {}
    if isinstance(dist, dict):
        f = dist.get("furlongs")
        if f is not None:
            try:
                return float(f)
            except (TypeError, ValueError):
                pass
        yards = dist.get("yards")
        if yards:
            try:
                return round(float(yards) / 220.0, 1)
            except (TypeError, ValueError):
                pass
    if runners_json:
        try:
            return float(runners_json[0].get("distanceFurlongRounded"))
        except (TypeError, ValueError):
            return None
    return None


def fetch_historical_racecards_on_date(
    card_date: str,
    *,
    regions: tuple[str, ...] = ("gb", "ire"),
    timeout_sec: int = 300,
) -> Path:
    """
    Fetch racecards for an absolute date using RP JSON APIs only.
    Writes vendor/rpscrape/racecards/{card_date}.json compatible with parse_racecard_json.
    """
    import os

    prev_cwd = os.getcwd()
    os.chdir(VENDOR_SCRIPTS)
    get_meetings, load_field_config, parse_runners, NetworkClient, Stats = _import_vendor()
    config = load_field_config()
    data_opts = config.setdefault("data_collection", {})
    data_opts["fetch_profiles"] = False
    data_opts["fetch_stats"] = True

    try:
        env = _sync_rpscrape_dotenv()
        client = NetworkClient(
            email=env.get("EMAIL"),
            access_token=env.get("ACCESS_TOKEN"),
            timeout=max(14, min(timeout_sec, 60)),
        )
        meetings_by_date = get_meetings(client, [card_date])
        meetings = meetings_by_date.get(card_date) or []
        if not meetings:
            raise RuntimeError(f"No RP meetings for {card_date}")

        allowed = {r.lower() for r in regions}
        racecards: dict[str, dict[str, dict[str, dict[str, Any]]]] = defaultdict(
            lambda: defaultdict(dict)
        )
        races_written = 0

        for meeting in meetings:
            region = str(meeting.get("venueCountryCode") or "").lower()
            if allowed and region not in allowed:
                continue
            course = meeting.get("venueName") or meeting.get("diffusionVenueName") or "Unknown"

            for race in meeting.get("races") or []:
                race_id = race.get("raceId")
                if not race_id:
                    continue
                status_runners, resp_runners = client.get(
                    f"https://www.racingpost.com/profile/horse/data/cardrunners/{race_id}.json"
                )
                if status_runners != 200:
                    continue
                try:
                    runners_json = list(resp_runners.json()["runners"].values())
                except (KeyError, ValueError, AttributeError):
                    continue
                if not runners_json:
                    continue

                stats_obj = None
                status_stats, resp_stats = client.get(
                    f"https://www.racingpost.com/api/racing/free-stats-tab/?raceId={race_id}&date={card_date}"
                )
                if status_stats == 200:
                    try:
                        stats_obj = Stats(resp_stats.json())
                    except (KeyError, ValueError, TypeError):
                        stats_obj = None

                runners = parse_runners(stats_obj, runners_json, {}, config)
                off = _off_time(race)
                payload: dict[str, Any] = {
                    "race_id": int(race_id),
                    "date": card_date,
                    "region": region,
                    "course": course,
                    "off_time": off,
                    "race_name": race.get("raceTitle"),
                    "race_type": race.get("raceType"),
                    "race_class": race.get("raceClass"),
                    "going": race.get("going"),
                    "distance_f": _distance_f(race, runners_json),
                    "field_size": race.get("numberOfRunners") or len(runners_json),
                    "runners": [asdict(r) for r in runners],
                }
                racecards[region][course][off] = payload
                races_written += 1

        if races_written == 0:
            raise RuntimeError(f"No races scraped via API for {card_date}")

        RPSCRAPE_RACECARDS.mkdir(parents=True, exist_ok=True)
        out_path = RPSCRAPE_RACECARDS / f"{card_date}.json"
        import orjson

        out_path.write_bytes(orjson.dumps(racecards, option=orjson.OPT_INDENT_2))
        return out_path
    finally:
        os.chdir(prev_cwd)
