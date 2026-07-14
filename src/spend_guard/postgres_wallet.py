"""Postgres spend wallet — production HA profile for Spend Guard (#11)."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from spend_guard.wallet import (
    WalletLockedError,
    WalletState,
    _SCHEMA,
    _default_hold_ttl_seconds,
    _utc_now,
)  # noqa: F401

__all__ = ["PostgresSpendWallet", "WalletLockedError", "WalletState"]


def _import_psycopg():
    try:
        import psycopg
    except ImportError as exc:
        raise RuntimeError(
            "Postgres wallet requires: pip install 'hibs-racing[postgres]'"
        ) from exc
    return psycopg


def _run_schema(conn) -> None:
    for part in _SCHEMA.split(";"):
        sql = part.strip()
        if sql:
            conn.execute(sql)


class PostgresSpendWallet:
    """Reserve → settle semantics on Postgres (multi-instance Spend Guard)."""

    def __init__(
        self,
        dsn: str,
        *,
        wallet_id: str = "default",
        initial_balance: float = 1000.0,
        drift_threshold_pct: float = 0.5,
        rolling_window: int = 20,
        ledger_db: Path | None = None,
    ) -> None:
        self.dsn = dsn.strip()
        self.database = self.dsn
        self.wallet_id = wallet_id
        self.drift_threshold_pct = drift_threshold_pct
        self.rolling_window = rolling_window
        self.ledger_db = Path(ledger_db) if ledger_db else None
        self._lock = threading.Lock()
        self._spend_history: list[float] = []
        psycopg = _import_psycopg()
        with psycopg.connect(self.dsn) as conn:
            _run_schema(conn)
            conn.commit()
        self._init_db(initial_balance)
        if self.ledger_db is not None:
            self.rebuild_spend_history_from_ledger(self.ledger_db)

    def rebuild_spend_history_from_ledger(self, ledger_db: Path | str | None = None) -> int:
        from inst_spine.ledger_factory import is_postgres_dsn, open_ledger

        target = ledger_db or self.ledger_db
        if target is None:
            return 0
        if not is_postgres_dsn(target) and not Path(target).is_file():
            return 0
        ledger = open_ledger(target)
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

    def _connect(self):
        psycopg = _import_psycopg()
        return psycopg.connect(self.dsn)

    def _init_db(self, initial_balance: float) -> None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT wallet_id FROM spend_wallet WHERE wallet_id = %s",
                (self.wallet_id,),
            ).fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO spend_wallet (wallet_id, balance, reserved, locked) "
                    "VALUES (%s, %s, 0, 0)",
                    (self.wallet_id, initial_balance),
                )
                conn.commit()

    def get_state(self) -> WalletState:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT balance, reserved, locked, lock_reason FROM spend_wallet WHERE wallet_id = %s",
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
                conn.execute(
                    "UPDATE spend_wallet SET locked = 1, lock_reason = %s WHERE wallet_id = %s",
                    (reason, self.wallet_id),
                )
                conn.commit()

    def unlock(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "UPDATE spend_wallet SET locked = 0, lock_reason = '' WHERE wallet_id = %s",
                    (self.wallet_id,),
                )
                conn.commit()

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
                with conn.transaction():
                    existing = conn.execute(
                        "SELECT hold_id, status, amount FROM spend_holds "
                        "WHERE wallet_id = %s AND request_id = %s FOR UPDATE",
                        (self.wallet_id, request_id),
                    ).fetchone()
                    if existing:
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
                        "UPDATE spend_wallet SET reserved = reserved + %s WHERE wallet_id = %s",
                        (amount, self.wallet_id),
                    )
                    conn.execute(
                        "INSERT INTO spend_holds (hold_id, wallet_id, amount, request_id, status, created_at) "
                        "VALUES (%s, %s, %s, %s, 'reserved', %s)",
                        (hold_id, self.wallet_id, amount, request_id, _utc_now()),
                    )
            return True, "reserved", hold_id

    def settle(self, hold_id: str, *, actual_amount: float | None = None) -> tuple[bool, str]:
        actual = 0.0
        with self._lock:
            with self._connect() as conn:
                with conn.transaction():
                    row = conn.execute(
                        "SELECT amount, status FROM spend_holds WHERE hold_id = %s AND wallet_id = %s FOR UPDATE",
                        (hold_id, self.wallet_id),
                    ).fetchone()
                    if not row:
                        return False, "hold_not_found"
                    reserved_amt, status = float(row[0]), row[1]
                    if status == "settled":
                        return True, "already_settled"
                    if status != "reserved":
                        return False, f"hold_status:{status}"

                    actual = reserved_amt if actual_amount is None else actual_amount
                    if actual > reserved_amt:
                        return False, "actual_exceeds_hold"

                    conn.execute(
                        "UPDATE spend_wallet SET balance = balance - %s, reserved = reserved - %s "
                        "WHERE wallet_id = %s",
                        (actual, reserved_amt, self.wallet_id),
                    )
                    conn.execute(
                        "UPDATE spend_holds SET status = 'settled' WHERE hold_id = %s",
                        (hold_id,),
                    )

        self._spend_history.append(actual)
        self._check_drift(actual)
        state = self.get_state()
        if state.locked:
            return False, state.lock_reason
        return True, "settled"

    def release(self, hold_id: str) -> tuple[bool, str]:
        with self._lock:
            with self._connect() as conn:
                with conn.transaction():
                    row = conn.execute(
                        "SELECT amount, status FROM spend_holds WHERE hold_id = %s AND wallet_id = %s FOR UPDATE",
                        (hold_id, self.wallet_id),
                    ).fetchone()
                    if not row:
                        return False, "hold_not_found"
                    amount, status = float(row[0]), row[1]
                    if status != "reserved":
                        return False, f"hold_status:{status}"
                    conn.execute(
                        "UPDATE spend_wallet SET reserved = reserved - %s WHERE wallet_id = %s",
                        (amount, self.wallet_id),
                    )
                    conn.execute(
                        "UPDATE spend_holds SET status = 'released' WHERE hold_id = %s",
                        (hold_id,),
                    )
            return True, "released"

    def reap_expired_holds(self, *, ttl_seconds: int | None = None) -> int:
        ttl = ttl_seconds if ttl_seconds is not None else _default_hold_ttl_seconds()
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=ttl)
        cutoff_s = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
        reaped = 0
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    "SELECT hold_id FROM spend_holds "
                    "WHERE wallet_id = %s AND status = 'reserved' "
                    "AND created_at IS NOT NULL AND created_at != '' AND created_at < %s",
                    (self.wallet_id, cutoff_s),
                ).fetchall()
        for (hold_id,) in rows:
            ok, reason = self.release(str(hold_id))
            if ok:
                reaped += 1
        return reaped

    def to_dict(self) -> dict[str, Any]:
        s = self.get_state()
        return {
            "wallet_id": s.wallet_id,
            "balance": s.balance,
            "reserved": s.reserved,
            "available": s.available,
            "locked": s.locked,
            "lock_reason": s.lock_reason,
            "backend": "postgres",
        }
