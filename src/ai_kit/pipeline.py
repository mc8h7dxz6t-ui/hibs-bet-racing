"""Agent loop with Lamport-stepped checkpoints."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ai_kit.limits import ProviderRateLimiter
from inst_spine.clocks import LamportClock, utc_now_iso
from inst_spine.contracts import RunManifest, stable_id
from inst_spine.errors import RateLimitError
from inst_spine.ledger import AppendOnlyLedger


class ToolAuthorizationError(RuntimeError):
    """Raised when Agent Ledger denies a tool invocation."""


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
        agent_ledger_db: Path | None = None,
        agent_permit_db: Path | None = None,
    ) -> None:
        self.agent_id = agent_id
        self.checkpoint_db = checkpoint_db or Path(f"data/ai_kit_{agent_id}.sqlite")
        self.limiter = limiter or ProviderRateLimiter()
        self.clock = LamportClock(agent_id)
        self.trace = trace_ledger
        self.agent_ledger_db = agent_ledger_db
        self.agent_permit_db = agent_permit_db
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
            manifest = RunManifest(
                manifest_id=stable_id(self.agent_id, "step", str(step)),
                run_kind="ai_kit_checkpoint",
                config_hash=stable_id(self.agent_id, "config", "v1"),
                writer_id=self.agent_id,
                created_at=wall,
                extras={"step": step},
            )
            self.trace.append(
                event_type="agent_checkpoint",
                payload={"agent_id": self.agent_id, "step": step, "state_keys": sorted(state.keys())},
                manifest_id=manifest.manifest_id,
                metadata={"manifest_hash": manifest.manifest_hash},
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
        tool_name: str | None = None,
        tool_arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = dict(initial_state or {})
        if tool_name is None:
            tool_name = state.pop("__tool_name__", None)
        if tool_arguments is None:
            tool_arguments = state.pop("__tool_args__", None)
        cp = self.load_checkpoint()
        if cp and cp.step >= start_step:
            state = cp.state
            start_step = cp.step + 1
            self.clock.observe(cp.lamport_seq)

        for step in range(start_step, start_step + steps):
            if not self.limiter.acquire(provider, model):
                wait = self.limiter.wait_hint_seconds(provider, model)
                raise RateLimitError(
                    f"rate limit exceeded for {provider}/{model}",
                    retry_after_sec=wait,
                )
            permit_id: str | None = None
            if tool_name and self.agent_ledger_db is not None:
                from agent_ledger.integrate import authorize_tool_call, complete_tool_call

                auth = authorize_tool_call(
                    agent_id=self.agent_id,
                    tool_name=tool_name,
                    arguments=tool_arguments or {},
                    ledger_db=self.agent_ledger_db,
                    permit_db=self.agent_permit_db,
                    session_id=f"step-{step}",
                    idempotency_key=f"{self.agent_id}:{step}:{tool_name}",
                )
                if auth.get("decision") != "permit":
                    raise ToolAuthorizationError(
                        f"agent ledger denied {tool_name}: {auth.get('reason')}"
                    )
                permit_id = str(auth.get("permit_id") or "")
            state = step_fn(step, state)
            if permit_id and self.agent_ledger_db is not None:
                from agent_ledger.integrate import complete_tool_call

                complete_tool_call(
                    permit_id=permit_id,
                    result={"step": step, "state_keys": sorted(state.keys())},
                    ledger_db=self.agent_ledger_db,
                    permit_db=self.agent_permit_db,
                )
            self.save_checkpoint(step, state)
        return state
