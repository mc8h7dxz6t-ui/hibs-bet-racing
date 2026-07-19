"""Signed execution intent ledger — append-only audit for governor verdicts."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_LOCK = threading.Lock()
_GENESIS = "HIBS_RACING_EXEC_GENESIS_V1"


def _ledger_path() -> Path:
    raw = os.getenv("HIBS_EXEC_INTENT_LEDGER", "data/execution_intent.jsonl")
    return Path(raw)


def _prev_hash(path: Path) -> str:
    if not path.is_file() or path.stat().st_size == 0:
        return hashlib.sha256(_GENESIS.encode()).hexdigest()
    try:
        last = ""
        with open(path, "rb") as fh:
            fh.seek(max(0, path.stat().st_size - 4096))
            for line in fh.read().decode("utf-8", errors="replace").splitlines():
                if line.strip():
                    last = line
        if not last:
            return hashlib.sha256(_GENESIS.encode()).hexdigest()
        row = json.loads(last)
        return str(row.get("chain_hash") or hashlib.sha256(_GENESIS.encode()).hexdigest())
    except Exception:
        return hashlib.sha256(_GENESIS.encode()).hexdigest()


def append_execution_intent(
    *,
    verdict: Dict[str, Any],
    source: str = "governor",
    trace_id: Optional[str] = None,
) -> None:
    if os.getenv("HIBS_EXEC_INTENT_LEDGER_ENABLED", "1").strip().lower() in ("0", "false", "no"):
        return
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "unix": time.time(),
        "source": source,
        "trace_id": trace_id or verdict.get("trace_id") or verdict.get("idempotency_key"),
        "verdict": verdict,
    }
    payload = json.dumps(body, sort_keys=True, default=str)
    with _LOCK:
        prev = _prev_hash(path)
        chain_hash = hashlib.sha256(f"{prev}|{payload}".encode()).hexdigest()
        row = {**body, "prev_hash": prev, "chain_hash": chain_hash}
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
            if os.getenv("HIBS_EXEC_INTENT_FSYNC", "1").strip().lower() in ("1", "true", "yes"):
                fh.flush()
                os.fsync(fh.fileno())
