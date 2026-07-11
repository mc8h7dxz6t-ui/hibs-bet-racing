"""Redis guardrail client — atomic market steam/drift via EVAL."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional


class RedisGuardrailClient:
    """
    Multi-pod market velocity guard. Falls back to in-process dict when Redis absent.

    Env:
      REDIS_URL / HIBS_REDIS_URL
      HIBS_REDIS_MARKET_STEAM_SCRIPT — path override for market_steam.lua
    """

    def __init__(self, redis_url: Optional[str] = None, *, key_prefix: str = "hibs:steam:") -> None:
        self._url = redis_url or os.getenv("HIBS_REDIS_URL") or os.getenv("REDIS_URL") or ""
        self._prefix = key_prefix
        self._script_sha: Optional[str] = None
        self._memory: Dict[str, Dict[str, float]] = {}
        self._client = None
        if self._url:
            try:
                import redis

                self._client = redis.Redis.from_url(self._url, decode_responses=True)
                lua_path = Path(
                    os.getenv("HIBS_REDIS_MARKET_STEAM_SCRIPT")
                    or Path(__file__).resolve().parents[2] / "redis_scripts" / "market_steam.lua"
                )
                script = lua_path.read_text(encoding="utf-8")
                self._script_sha = self._client.script_load(script)
            except Exception:
                self._client = None

    def record_odds(
        self,
        runner_id: str,
        *,
        feed: str,
        odds: float,
        steam_threshold_pct: float = 8.0,
        drift_threshold_pct: float = 12.0,
    ) -> Dict[str, Any]:
        key = f"{self._prefix}{runner_id}"
        ts = int(time.time())
        if self._client and self._script_sha:
            raw = self._client.evalsha(
                self._script_sha,
                1,
                key,
                feed,
                str(odds),
                str(ts),
                str(steam_threshold_pct),
                str(drift_threshold_pct),
            )
            return json.loads(raw)
        return self._memory_fallback(key, feed, odds, steam_threshold_pct, drift_threshold_pct, ts)

    def _memory_fallback(
        self,
        key: str,
        feed: str,
        odds: float,
        steam_thr: float,
        drift_thr: float,
        ts: int,
    ) -> Dict[str, Any]:
        bucket = self._memory.setdefault(key, {})
        prev = bucket.get(feed)
        bucket[feed] = odds
        if prev is None or prev <= 1:
            return {"direction": "unknown", "gate": "proceed", "odds_now": odds, "prev_odds": None}
        change_pct = ((odds - prev) / prev) * 100.0
        direction = "flat"
        if change_pct <= -steam_thr:
            direction = "steam"
        elif change_pct >= drift_thr:
            direction = "drift"
        gate = "proceed"
        if direction == "steam":
            gate = "scale_up"
        elif direction == "drift":
            gate = "abort"
        return {
            "direction": direction,
            "change_pct": change_pct,
            "drift_delta": odds - prev,
            "gate": gate,
            "prev_odds": prev,
            "odds_now": odds,
            "feed": feed,
        }
