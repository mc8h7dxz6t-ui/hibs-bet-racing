"""mmap-backed write-ahead capture (.wrcap) for raw ingress bytes before parsing."""

from __future__ import annotations

import hashlib
import mmap
import os
import struct
import threading
import time
from pathlib import Path
from typing import Any, BinaryIO, Dict, Optional


_MAGIC = b"WRCAP1\0\0"
_HEADER = struct.Struct("<8sQQ")  # magic, seq, payload_len


class WebhookWal:
    """
    Sequential durable capture of raw payload bytes.

    Files: `{root}/{stream}/{seq:012d}.wrcap`
    Offset pointer: `{root}/{stream}/offset.ptr`
    """

    def __init__(self, root: Path, stream: str) -> None:
        self.root = Path(root)
        self.stream = stream
        self.dir = self.root / stream
        self.dir.mkdir(parents=True, exist_ok=True)
        self._offset_path = self.dir / "offset.ptr"
        self._lock = threading.Lock()
        if not self._offset_path.exists():
            self._offset_path.write_text("0", encoding="utf-8")

    def _next_seq(self) -> int:
        with self._lock:
            seq = int(self._offset_path.read_text(encoding="utf-8").strip() or "0")
            self._offset_path.write_text(str(seq + 1), encoding="utf-8")
            return seq

    def append_raw(
        self,
        payload: bytes,
        *,
        meta: Optional[Dict[str, Any]] = None,
    ) -> Path:
        seq = self._next_seq()
        path = self.dir / f"{seq:012d}.wrcap"
        header = _HEADER.pack(_MAGIC, seq, len(payload))
        with open(path, "wb") as fh:
            fh.write(header)
            fh.write(payload)
            if meta:
                meta_bytes = repr(meta).encode("utf-8")[:512]
                fh.write(struct.pack("<H", len(meta_bytes)))
                fh.write(meta_bytes)
            fh.flush()
            os.fsync(fh.fileno())
        return path

    @staticmethod
    def read_record(path: Path) -> tuple[int, bytes]:
        with open(path, "r+b") as fh:
            mm = mmap.mmap(fh.fileno(), 0)
            try:
                magic, seq, length = _HEADER.unpack_from(mm, 0)
                if magic != _MAGIC:
                    raise ValueError(f"bad wrcap magic in {path}")
                payload = mm[_HEADER.size : _HEADER.size + length]
                return seq, bytes(payload)
            finally:
                mm.close()


def capture_before_parse(
    stream: str,
    payload: bytes,
    *,
    root: Optional[Path] = None,
    source: str = "unknown",
) -> Path:
    """Ingress helper — always WAL raw bytes before JSON parse."""
    wal_root = root or Path(os.getenv("HIBS_WAL_ROOT", "/var/log/hibs-bet/wal"))
    wal = WebhookWal(wal_root, stream)
    return wal.append_raw(
        payload,
        meta={"source": source, "sha256": hashlib.sha256(payload).hexdigest(), "ts": time.time()},
    )
