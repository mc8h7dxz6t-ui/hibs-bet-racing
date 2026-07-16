"""Background async daemon — stream ingestion + execution governor + liquidity router."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from hibs_racing.trading.config import liquidity_router_active, liquidity_router_poll_seconds, live_trading_enabled
from hibs_racing.trading.execution_governor import ExecutionGovernor
from hibs_racing.trading.liquidity_router import LiquidityRouter
from hibs_racing.trading.stream_listener import StreamListener, obtain_matchbook_session_token
from hibs_racing.trading.store import ensure_trading_schema

logger = logging.getLogger(__name__)


@dataclass
class TradingDaemon:
    """Runs stream listener as async background task — no Flask/template coupling."""

    listener: StreamListener = field(default_factory=StreamListener)
    governor: ExecutionGovernor | None = None
    router: LiquidityRouter | None = None
    _tasks: list[asyncio.Task] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        if self.governor is None:
            self.governor = ExecutionGovernor(cache=self.listener.cache)
        if self.router is None:
            self.router = LiquidityRouter(cache=self.listener.cache)
        ensure_trading_schema()

    async def start(self) -> None:
        token = await asyncio.to_thread(obtain_matchbook_session_token)
        if token:
            self.listener.session_token = token
        logger.info(
            "trading daemon starting live_trading=%s router=%s stream_url=%r",
            live_trading_enabled(),
            liquidity_router_active(),
            self.listener.resolve_ws_url() or "(inject-only)",
        )
        self._tasks = [
            asyncio.create_task(self.listener.run(), name="hibs-stream-listener"),
            asyncio.create_task(self._liquidity_router_loop(), name="hibs-liquidity-router"),
        ]

    async def _liquidity_router_loop(self) -> None:
        interval = liquidity_router_poll_seconds()
        while True:
            try:
                assert self.router is not None
                report = await asyncio.to_thread(self.router.process_tick)
                if report.get("routed") or report.get("hedged"):
                    logger.info("liquidity router tick: %s", report)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("liquidity router tick failed: %s", exc)
            await asyncio.sleep(interval)

    async def stop(self) -> None:
        await self.listener.stop()
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()

    async def run_until_stopped(self) -> None:
        await self.start()
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await self.stop()

    def submit_order(self, payload: dict[str, Any]) -> dict[str, Any]:
        assert self.governor is not None
        return self.governor.dispatch(payload).to_dict()

    def status(self) -> dict[str, Any]:
        assert self.governor is not None
        assert self.router is not None
        router_report = self.router.process_tick()
        return {
            "live_trading_enabled": live_trading_enabled(),
            "liquidity_router_active": liquidity_router_active(),
            "stream": self.listener.stats.to_dict(),
            "cache_size": self.listener.cache.size(),
            "wallet_id": self.governor.wallet_id,
            "liquidity_router_last": router_report,
        }


async def run_trading_daemon() -> None:
    daemon = TradingDaemon()
    await daemon.run_until_stopped()


def run_trading_daemon_sync() -> None:
    asyncio.run(run_trading_daemon())
