from __future__ import annotations

import os
import time
from typing import Any

from hibs_racing.config import load_config

# Env keys override ingest/config.yaml rate_limits.* (seconds unless noted).
_ENV_MAP = {
    "racing_api_pause_sec": "RACING_API_PAUSE_SEC",
    "racing_api_429_pause_sec": "RACING_API_429_PAUSE_SEC",
    "racing_api_429_retries": "RACING_API_429_RETRIES",
    "rp_scrape_day_pause_sec": "RP_SCRAPE_DAY_PAUSE_SEC",
    "rp_racecard_region_pause_sec": "RP_RACECARD_REGION_PAUSE_SEC",
    "rp_verdict_race_pause_sec": "RP_VERDICT_RACE_PAUSE_SEC",
    "rp_verdict_workers": "RP_VERDICT_WORKERS",
    "rp_verdict_max_races": "RP_VERDICT_MAX_RACES",
}


def rate_limits(cfg: dict | None = None) -> dict[str, Any]:
    """Merged rate-limit settings — keep external sources unblocked."""
    base = dict((cfg or load_config()).get("rate_limits", {}))
    defaults = {
        "racing_api_pause_sec": 1.5,
        "racing_api_429_pause_sec": 8.0,
        "racing_api_429_retries": 4,
        "rp_scrape_day_pause_sec": 4.0,
        "rp_racecard_region_pause_sec": 5.0,
        "rp_verdict_race_pause_sec": 1.2,
        "rp_verdict_workers": 2,
        "rp_verdict_max_races": 20,
        "oddschecker_pause_sec": 1.5,
    }
    out = {**defaults, **base}
    for key, env_name in _ENV_MAP.items():
        raw = os.environ.get(env_name, "").strip()
        if not raw:
            continue
        if key.endswith("_retries") or key.endswith("_workers") or key.endswith("_max_races"):
            try:
                out[key] = int(raw)
            except ValueError:
                pass
        else:
            try:
                out[key] = float(raw)
            except ValueError:
                pass
    return out


def pause_sec(key: str, *, cfg: dict | None = None) -> float:
    limits = rate_limits(cfg)
    try:
        return max(0.0, float(limits.get(key, 0.0)))
    except (TypeError, ValueError):
        return 0.0


def int_limit(key: str, *, cfg: dict | None = None) -> int:
    limits = rate_limits(cfg)
    try:
        return max(0, int(limits.get(key, 0)))
    except (TypeError, ValueError):
        return 0


def polite_sleep(key: str, *, cfg: dict | None = None, label: str | None = None) -> None:
    """Sleep between outbound calls — no-op when pause is 0."""
    sec = pause_sec(key, cfg=cfg)
    if sec > 0:
        time.sleep(sec)


def racing_api_pause(cfg: dict | None = None) -> float:
    return pause_sec("racing_api_pause_sec", cfg=cfg)


def rp_scrape_day_pause(cfg: dict | None = None) -> float:
    return pause_sec("rp_scrape_day_pause_sec", cfg=cfg)


def rp_racecard_region_pause(cfg: dict | None = None) -> float:
    return pause_sec("rp_racecard_region_pause_sec", cfg=cfg)


def rp_verdict_race_pause(cfg: dict | None = None) -> float:
    return pause_sec("rp_verdict_race_pause_sec", cfg=cfg)


def rp_verdict_workers(cfg: dict | None = None) -> int:
    return max(1, int_limit("rp_verdict_workers", cfg=cfg))


def rp_verdict_max_races(cfg: dict | None = None) -> int:
    return max(1, int_limit("rp_verdict_max_races", cfg=cfg))
