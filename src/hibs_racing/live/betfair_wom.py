"""Phase C — Betfair WOM / tick velocity (stub; enable after Phase A/B proof)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WOMSnapshot:
    selection_id: int
    back_volume: float
    lay_volume: float
    best_back: float
    best_lay: float
    tick_velocity_per_min: float

    @property
    def wom_ratio(self) -> float:
        total = self.back_volume + self.lay_volume
        if total <= 0:
            return 0.5
        return self.back_volume / total


def stake_multiplier_from_wom(
    snapshot: WOMSnapshot,
    *,
    base_cap: float = 1.0,
    max_cap: float = 1.25,
    min_velocity: float = 0.5,
) -> float:
    """
    Scale stake only when model already flagged value AND odds steam confirms.
    Never bypass Kelly caps — aligns with hibs-bet fractional policy.
    """
    if snapshot.tick_velocity_per_min < min_velocity:
        return base_cap
    if snapshot.wom_ratio > 0.6 and snapshot.tick_velocity_per_min > 1.0:
        return min(max_cap, base_cap * 1.15)
    return base_cap


class BetfairStreamClient:
    """Placeholder — wire Betfair Exchange Stream API in Phase C."""

    def __init__(self, app_key: str, username: str, password: str) -> None:
        self.app_key = app_key
        self.username = username
        self.password = password

    def connect(self) -> None:
        raise NotImplementedError(
            "Phase C: implement Betfair stream after offline backtest passes."
        )


class BetfairExecutionClient:
    """Transactional stub — placeOrders via Sports API (live gated by HIBS_EXECUTION_LIVE)."""

    def __init__(self, app_key: str, username: str, password: str) -> None:
        self.app_key = app_key
        self.username = username
        self.password = password
        self._session_token: str | None = None

    def login(self) -> str:
        raise NotImplementedError(
            "Phase C: implement Betfair SSO login + session token before live routing."
        )

    def place_orders(self, instructions: list[dict]) -> dict:
        if not instructions:
            return {"status": "SUCCESS", "instructionReports": []}
        raise NotImplementedError(
            "Phase C: wire SportsAPING/v1.0/placeOrders — use execution router dry_run until mapped."
        )
