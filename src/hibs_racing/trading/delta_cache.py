"""Thread-safe in-memory market delta cache."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PriceTick:
    market_id: str
    runner_id: str
    back_odds: float | None
    lay_odds: float | None
    updated_at_ms: int
    seq: int | None = None
    back_volume: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "market_id": self.market_id,
            "runner_id": self.runner_id,
            "back_odds": self.back_odds,
            "lay_odds": self.lay_odds,
            "updated_at_ms": self.updated_at_ms,
            "seq": self.seq,
            "back_volume": self.back_volume,
            "matchbook_back_volume": self.back_volume,
        }


class MarketDeltaCache:
    """Fast thread-safe cache keyed by market_id:runner_id."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._ticks: dict[str, PriceTick] = {}
        self._last_packet_at_ms: int | None = None

    @staticmethod
    def _key(market_id: str, runner_id: str) -> str:
        return f"{market_id}:{runner_id}"

    def apply_delta(self, delta: dict[str, Any]) -> PriceTick | None:
        market_id = str(delta.get("market_id") or delta.get("market-id") or "")
        runner_id = str(delta.get("runner_id") or delta.get("runner-id") or "")
        if not market_id or not runner_id:
            return None
        back = delta.get("back_odds", delta.get("back-odds"))
        lay = delta.get("lay_odds", delta.get("lay-odds"))
        vol = delta.get("matchbook_back_volume", delta.get("back_volume", delta.get("back_liquidity")))
        ts_ms = int(delta.get("ts_ms") or delta.get("timestamp_ms") or time.time() * 1000)
        seq_raw = delta.get("seq")
        seq = int(seq_raw) if seq_raw is not None else None
        tick = PriceTick(
            market_id=market_id,
            runner_id=runner_id,
            back_odds=float(back) if back is not None else None,
            lay_odds=float(lay) if lay is not None else None,
            updated_at_ms=ts_ms,
            seq=seq,
            back_volume=float(vol) if vol is not None else None,
        )
        key = self._key(market_id, runner_id)
        with self._lock:
            self._ticks[key] = tick
            self._last_packet_at_ms = ts_ms
        return tick

    def get(self, market_id: str, runner_id: str) -> PriceTick | None:
        key = self._key(market_id, runner_id)
        with self._lock:
            return self._ticks.get(key)

    def last_packet_at_ms(self) -> int | None:
        with self._lock:
            return self._last_packet_at_ms

    def snapshot(self) -> list[dict[str, Any]]:
        with self._lock:
            return [tick.to_dict() for tick in self._ticks.values()]

    def size(self) -> int:
        with self._lock:
            return len(self._ticks)
