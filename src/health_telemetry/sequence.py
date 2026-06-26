"""Per-device monotonic sequence gate — replay / gap detection."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from inst_spine.errors import IngestValidationError

_SCHEMA = """
CREATE TABLE IF NOT EXISTS device_sequence (
    device_id TEXT PRIMARY KEY,
    last_seq INTEGER NOT NULL DEFAULT 0,
    batch_count INTEGER NOT NULL DEFAULT 0
);
"""


class DeviceSequenceStore:
    """Persist last accepted seq per device — survives gateway restarts."""

    def __init__(self, database: Path) -> None:
        self.database = Path(database)
        self.database.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.database) as conn:
            conn.executescript(_SCHEMA)

    @classmethod
    def for_ledger(cls, ledger_db: Path) -> DeviceSequenceStore:
        path = Path(ledger_db).with_name(Path(ledger_db).stem + "_sequence.sqlite")
        return cls(path)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.database, timeout=30.0)

    def last_seq(self, device_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT last_seq FROM device_sequence WHERE device_id = ?",
                (device_id,),
            ).fetchone()
        return int(row[0]) if row else 0

    def validate_and_commit(
        self,
        device_id: str,
        packet_seqs: list[int],
        *,
        allow_replay: bool = False,
        max_gap: int = 0,
    ) -> dict[str, int | bool]:
        """
        Fail-closed on backward seq or gap > max_gap.
        max_gap=0 means strictly consecutive (+1).
        """
        if not packet_seqs:
            raise IngestValidationError("sequence gate: empty packet seq list")

        ordered = sorted(packet_seqs)
        if ordered != packet_seqs:
            raise IngestValidationError("sequence gate: packets must be ordered by seq")

        last = self.last_seq(device_id)
        expected_start = last + 1 if last > 0 else packet_seqs[0]

        if last > 0 and packet_seqs[0] < last and not allow_replay:
            raise IngestValidationError(
                f"sequence gate: backward seq device={device_id} "
                f"last={last} got={packet_seqs[0]}"
            )

        if last > 0 and packet_seqs[0] != expected_start and not allow_replay:
            gap = packet_seqs[0] - expected_start
            if gap != 0:
                if gap > max_gap:
                    raise IngestValidationError(
                        f"sequence gate: gap device={device_id} "
                        f"expected>={expected_start} got={packet_seqs[0]} gap={gap}"
                    )

        for i in range(1, len(packet_seqs)):
            step = packet_seqs[i] - packet_seqs[i - 1]
            if step <= 0:
                raise IngestValidationError(
                    f"sequence gate: non-monotonic within batch at index {i}"
                )
            if max_gap == 0 and step != 1:
                raise IngestValidationError(
                    f"sequence gate: non-consecutive within batch seq step={step}"
                )
            if step > max_gap + 1:
                raise IngestValidationError(
                    f"sequence gate: intra-batch gap step={step} max_gap={max_gap}"
                )

        new_last = packet_seqs[-1]
        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO device_sequence (device_id, last_seq, batch_count)
                VALUES (?, ?, 1)
                ON CONFLICT(device_id) DO UPDATE SET
                    last_seq = excluded.last_seq,
                    batch_count = batch_count + 1
                """,
                (device_id, new_last),
            )
            conn.commit()

        return {
            "previous_seq": last,
            "last_seq": new_last,
            "batch_packets": len(packet_seqs),
            "gap_detected": last > 0 and packet_seqs[0] != expected_start,
        }
