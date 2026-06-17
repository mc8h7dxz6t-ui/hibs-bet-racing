"""Agent loop with Lamport-stepped checkpoints."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_kit.limits import ProviderRateLimiter
from inst_spine.clocks import LamportClock, utc_now_iso
from inst_spine.ledger import AppendOnlyLedger


@dataclass
class AgentCheckpoint:
    step: int
    lamport_seq: int
    state: dict[str, Any]
    wall_time_utc: str


class AgentLoop:
    """
    Minimal agentic state loop:
      rate limit → step fn → validate → checkpoint → trace log
    """

    def __init__(
        self,
        *,
        agent_id: str = "agent",
        checkpoint_db: Path | None = None,
        trace_ledger: AppendOnlyLedger | None = None,
        limiter: ProviderRateLimiter | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.checkpoint_db = checkpoint_db or Path(f"data/ai_kit_{agent_id}.sqlite")
        self.limiter = limiter or ProviderRateLimiter()
        self.clock = LamportClock(agent_id)
        self.trace = trace_ledger
        self._init_checkpoint_db()

    def _init_checkpoint_db(self) -> None:
        self.checkpoint_db.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.checkpoint_db) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS checkpoints (
                    step INTEGER PRIMARY KEY,
                    lamport_seq INTEGER NOT NULL,
                    wall_time_utc TEXT NOT NULL,
                    state_json TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def load_checkpoint(self) -> AgentCheckpoint | None:
        with sqlite3.connect(self.checkpoint_db) as conn:
            row = conn.execute(
                "SELECT step, lamport_seq, wall_time_utc, state_json FROM checkpoints ORDER BY step DESC LIMIT 1"
            ).fetchone()
        if not row:
            return None
        return AgentCheckpoint(
            step=int(row[0]),
            lamport_seq=int(row[1]),
            state=json.loads(row[3]),
            wall_time_utc=str(row[2]),
        )

    def save_checkpoint(self, step: int, state: dict[str, Any]) -> AgentCheckpoint:
        lamport = self.clock.tick()
        wall = utc_now_iso()
        with sqlite3.connect(self.checkpoint_db) as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO checkpoints (step, lamport_seq, wall_time_utc, state_json)
                VALUES (?, ?, ?, ?)
                """,
                (step, lamport, wall, json.dumps(state, sort_keys=True)),
            )
            conn.commit()
        cp = AgentCheckpoint(step=step, lamport_seq=lamport, state=state, wall_time_utc=wall)
        if self.trace:
            self.trace.append(
                event_type="agent_checkpoint",
                payload={"agent_id": self.agent_id, "step": step, "state_keys": sorted(state.keys())},
            )
        return cp

    def run_steps(
        self,
        *,
        start_step: int,
        steps: int,
        step_fn: Callable[[int, dict[str, Any]], dict[str, Any]],
        provider: str = "openai",
        model: str = "gpt-4o-mini",
        initial_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = dict(initial_state or {})
        cp = self.load_checkpoint()
        if cp and cp.step >= start_step:
            state = cp.state
            start_step = cp.step + 1
            self.clock.observe(cp.lamport_seq)

        for step in range(start_step, start_step + steps):
            if not self.limiter.acquire(provider, model):
                raise RuntimeError(
                    f"rate limit exceeded; retry in {self.limiter.wait_hint_seconds(provider, model):.2f}s"
                )
            state = step_fn(step, state)
            self.save_checkpoint(step, state)
        return state
