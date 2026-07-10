"""Reserve → settle wallet with drift lockout."""

from __future__ import annotations

import sqlite3
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class WalletLockedError(RuntimeError):
    """Raised when wallet is locked due to spend drift."""


@dataclass
class WalletState:
    wallet_id: str
    balance: float
    reserved: float
    locked: bool
    lock_reason: str = ""

    @property
    def available(self) -> float:
        return max(0.0, self.balance - self.reserved)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS spend_wallet (
    wallet_id TEXT PRIMARY KEY,
    balance REAL NOT NULL,
    reserved REAL NOT NULL DEFAULT 0,
    locked INTEGER NOT NULL DEFAULT 0,
    lock_reason TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS spend_holds (
    hold_id TEXT PRIMARY KEY,
    wallet_id TEXT NOT NULL,
    amount REAL NOT NULL,
    request_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'reserved',
    created_at TEXT NOT NULL DEFAULT ''
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_spend_holds_request
    ON spend_holds(wallet_id, request_id);
"""


class SpendWallet:
    """
    Postgres-style reserve → settle semantics on SQLite with IMMEDIATE transactions.
    Drift lockout when weekend spend exceeds threshold vs rolling average.
    """

    def __init__(
        self,
        database: Path,
        *,
        wallet_id: str = "default",
        initial_balance: float = 1000.0,
        drift_threshold_pct: float = 0.5,
        rolling_window: int = 20,
        ledger_db: Path | None = None,
    ) -> None:
        self.database = Path(database)
        self.wallet_id = wallet_id
        self.drift_threshold_pct = drift_threshold_pct
        self.rolling_window = rolling_window
        self.ledger_db = Path(ledger_db) if ledger_db else None
        self._lock = threading.Lock()
        self._spend_history: list[float] = []
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self._init_db(initial_balance)
        if self.ledger_db is not None:
            self.rebuild_spend_history_from_ledger(self.ledger_db)

    def rebuild_spend_history_from_ledger(self, ledger_db: Path | None = None) -> int:
        """Rebuild in-memory drift window from durable spend_guard settle events."""
        from inst_spine.ledger import AppendOnlyLedger

        path = Path(ledger_db or self.ledger_db or "")
        if not path.is_file():
            return 0
        ledger = AppendOnlyLedger(path)
        amounts: list[float] = []
        for row in ledger.list_entries():
            if row.get("event_type") != "spend_guard":
                continue
            payload = row.get("payload") or {}
            if payload.get("phase") != "settle":
                continue
            if str(payload.get("decision")) != "approve":
                continue
            amounts.append(float(payload.get("estimated_cost") or 0.0))
        self._spend_history = amounts[-self.rolling_window :]
        return len(amounts)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.database, timeout=30.0, isolation_level=None)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self, initial_balance: float) -> None:
        with self._connect() as conn:
            conn.executescript(_SCHEMA)
            row = conn.execute(
                "SELECT wallet_id FROM spend_wallet WHERE wallet_id = ?",
                (self.wallet_id,),
            ).fetchone()
            if not row:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "INSERT INTO spend_wallet (wallet_id, balance, reserved, locked) VALUES (?, ?, 0, 0)",
                    (self.wallet_id, initial_balance),
                )
                conn.execute("COMMIT")

    def get_state(self) -> WalletState:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT balance, reserved, locked, lock_reason FROM spend_wallet WHERE wallet_id = ?",
                (self.wallet_id,),
            ).fetchone()
            if not row:
                raise RuntimeError(f"wallet {self.wallet_id} not found")
            return WalletState(
                wallet_id=self.wallet_id,
                balance=float(row[0]),
                reserved=float(row[1]),
                locked=bool(row[2]),
                lock_reason=str(row[3] or ""),
            )

    def lock(self, reason: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE spend_wallet SET locked = 1, lock_reason = ? WHERE wallet_id = ?",
                    (reason, self.wallet_id),
                )
                conn.execute("COMMIT")

    def unlock(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                conn.execute(
                    "UPDATE spend_wallet SET locked = 0, lock_reason = '' WHERE wallet_id = ?",
                    (self.wallet_id,),
                )
                conn.execute("COMMIT")

    def _check_drift(self, amount: float) -> None:
        if not self._spend_history:
            return
        window = self._spend_history[-self.rolling_window :]
        avg = sum(window) / len(window)
        if avg <= 0:
            return
        if amount > avg * (1.0 + self.drift_threshold_pct):
            self.lock(f"DRIFT_THRESHOLD_EXCEEDED: amount={amount:.4f} avg={avg:.4f}")

    def reserve(self, amount: float, *, request_id: str) -> tuple[bool, str, str | None]:
        if amount <= 0:
            return False, "invalid_amount", None
        with self._lock:
            state = self.get_state()
            if state.locked:
                return False, state.lock_reason or "wallet_locked", None
            if state.available < amount:
                return False, "insufficient_balance", None

            hold_id = str(uuid.uuid4())
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                existing = conn.execute(
                    "SELECT hold_id, status, amount FROM spend_holds WHERE wallet_id = ? AND request_id = ?",
                    (self.wallet_id, request_id),
                ).fetchone()
                if existing:
                    conn.execute("ROLLBACK")
                    hold_id_existing, status_existing, amount_existing = (
                        str(existing[0]),
                        str(existing[1]),
                        float(existing[2]),
                    )
                    if status_existing == "reserved":
                        if amount_existing != amount:
                            return (
                                False,
                                "duplicate_request_id_amount_mismatch",
                                hold_id_existing,
                            )
                        return True, "already_reserved", hold_id_existing
                    if status_existing == "settled":
                        return True, "already_settled", hold_id_existing
                    return False, f"duplicate_request_id_status:{status_existing}", hold_id_existing

                conn.execute(
                    "UPDATE spend_wallet SET reserved = reserved + ? WHERE wallet_id = ?",
                    (amount, self.wallet_id),
                )
                conn.execute(
                    "INSERT INTO spend_holds (hold_id, wallet_id, amount, request_id, status) "
                    "VALUES (?, ?, ?, ?, 'reserved')",
                    (hold_id, self.wallet_id, amount, request_id),
                )
                conn.execute("COMMIT")
            return True, "reserved", hold_id

    def settle(self, hold_id: str, *, actual_amount: float | None = None) -> tuple[bool, str]:
        actual = 0.0
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT amount, status, request_id FROM spend_holds WHERE hold_id = ? AND wallet_id = ?",
                    (hold_id, self.wallet_id),
                ).fetchone()
                if not row:
                    conn.execute("ROLLBACK")
                    return False, "hold_not_found"
                reserved_amt, status, _req = float(row[0]), row[1], row[2]
                if status == "settled":
                    conn.execute("ROLLBACK")
                    return True, "already_settled"
                if status != "reserved":
                    conn.execute("ROLLBACK")
                    return False, f"hold_status:{status}"

                actual = reserved_amt if actual_amount is None else actual_amount
                if actual > reserved_amt:
                    conn.execute("ROLLBACK")
                    return False, "actual_exceeds_hold"

                conn.execute(
                    "UPDATE spend_wallet SET balance = balance - ?, reserved = reserved - ? WHERE wallet_id = ?",
                    (actual, reserved_amt, self.wallet_id),
                )
                conn.execute(
                    "UPDATE spend_holds SET status = 'settled' WHERE hold_id = ?",
                    (hold_id,),
                )
                conn.execute("COMMIT")

        self._spend_history.append(actual)
        self._check_drift(actual)
        state = self.get_state()
        if state.locked:
            return False, state.lock_reason
        return True, "settled"

    def release(self, hold_id: str) -> tuple[bool, str]:
        with self._lock:
            with self._connect() as conn:
                conn.execute("BEGIN IMMEDIATE")
                row = conn.execute(
                    "SELECT amount, status FROM spend_holds WHERE hold_id = ? AND wallet_id = ?",
                    (hold_id, self.wallet_id),
                ).fetchone()
                if not row:
                    conn.execute("ROLLBACK")
                    return False, "hold_not_found"
                amount, status = float(row[0]), row[1]
                if status != "reserved":
                    conn.execute("ROLLBACK")
                    return False, f"hold_status:{status}"
                conn.execute(
                    "UPDATE spend_wallet SET reserved = reserved - ? WHERE wallet_id = ?",
                    (amount, self.wallet_id),
                )
                conn.execute(
                    "UPDATE spend_holds SET status = 'released' WHERE hold_id = ?",
                    (hold_id,),
                )
                conn.execute("COMMIT")
            return True, "released"

    def to_dict(self) -> dict[str, Any]:
        s = self.get_state()
        return {
            "wallet_id": s.wallet_id,
            "balance": s.balance,
            "reserved": s.reserved,
            "available": s.available,
            "locked": s.locked,
            "lock_reason": s.lock_reason,
        }
