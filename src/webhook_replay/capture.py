"""Memory-mapped-friendly webhook capture store."""

from __future__ import annotations

import hashlib
import json
import mmap
import struct
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


CAPTURE_MAGIC = b"WRCAP\x01"
HEADER_STRUCT = struct.Struct(">6sI")  # magic + header_json_len


@dataclass
class CaptureManifest:
    """Metadata for one captured webhook ingress."""

    capture_id: str
    tenant_id: str
    provider: str
    headers: dict[str, str]
    received_at_utc: str
    lamport_seq: int = 0
    target_forward_url: str = ""
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def payload_sha256(self) -> str:
        return str(self.extras.get("payload_sha256") or "")

    def to_dict(self) -> dict[str, Any]:
        return {
            "capture_id": self.capture_id,
            "tenant_id": self.tenant_id,
            "provider": self.provider,
            "headers": self.headers,
            "received_at_utc": self.received_at_utc,
            "lamport_seq": self.lamport_seq,
            "target_forward_url": self.target_forward_url,
            "extras": self.extras,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaptureManifest:
        return cls(
            capture_id=str(data["capture_id"]),
            tenant_id=str(data.get("tenant_id") or ""),
            provider=str(data.get("provider") or "generic"),
            headers={str(k): str(v) for k, v in (data.get("headers") or {}).items()},
            received_at_utc=str(data.get("received_at_utc") or ""),
            lamport_seq=int(data.get("lamport_seq") or 0),
            target_forward_url=str(data.get("target_forward_url") or ""),
            extras=dict(data.get("extras") or {}),
        )


class CaptureStore:
    """
    Single-file capture format: MAGIC + u32 header_len + JSON header + raw body.
    Readable via mmap for air-gapped replay.
    """

    def __init__(self, base_dir: Path) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, capture_id: str) -> Path:
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in capture_id)
        return self.base_dir / f"{safe}.wrcap"

    def write(
        self,
        manifest: CaptureManifest,
        body: bytes,
    ) -> Path:
        import hashlib

        header = manifest.to_dict()
        header["payload_sha256"] = hashlib.sha256(body).hexdigest()
        header["payload_size"] = len(body)
        header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
        out = self._path_for(manifest.capture_id)
        with open(out, "wb") as fh:
            fh.write(HEADER_STRUCT.pack(CAPTURE_MAGIC, len(header_bytes)))
            fh.write(header_bytes)
            fh.write(body)
        manifest.extras["payload_sha256"] = header["payload_sha256"]
        manifest.extras["payload_size"] = header["payload_size"]
        return out

    def read(self, path: Path) -> tuple[CaptureManifest, bytes]:
        path = Path(path)
        with open(path, "rb") as fh:
            mm = mmap.mmap(fh.fileno(), 0, access=mmap.ACCESS_READ)
            try:
                magic, header_len = HEADER_STRUCT.unpack(mm[: HEADER_STRUCT.size])
                if magic != CAPTURE_MAGIC:
                    raise ValueError(f"invalid capture magic in {path}")
                start = HEADER_STRUCT.size
                header_end = start + header_len
                header = json.loads(mm[start:header_end].decode("utf-8"))
                manifest = CaptureManifest.from_dict(header)
                if "payload_sha256" in header:
                    manifest.extras["payload_sha256"] = header["payload_sha256"]
                if "payload_size" in header:
                    manifest.extras["payload_size"] = header["payload_size"]
                body = bytes(mm[header_end:])
                return manifest, body
            finally:
                mm.close()

    def list_captures(self) -> list[Path]:
        return sorted(self.base_dir.glob("*.wrcap"))

    def read_by_id(self, capture_id: str) -> tuple[CaptureManifest, bytes]:
        return self.read(self._path_for(capture_id))
