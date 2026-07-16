"""Minimal async WebSocket client transport (RFC6455, text frames only)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import ssl
from typing import Mapping

logger = logging.getLogger(__name__)

_WEBSOCKET_GUID = "258EAFA5-E914-47DA-95CA-CAB5BE011C11"


class WebSocketTransportError(RuntimeError):
    """Raised when handshake or framing fails."""


class AsyncWebSocketTransport:
    """Small dependency-free transport for ingestion-only streaming clients."""

    def __init__(self) -> None:
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._writer is not None and not self._writer.is_closing()

    async def connect(
        self,
        host: str,
        path: str,
        *,
        port: int = 443,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        if self.is_connected:
            return
        ssl_context = ssl.create_default_context()
        reader, writer = await asyncio.open_connection(host, port, ssl=ssl_context)
        key = base64.b64encode(secrets.token_bytes(16)).decode("ascii")
        header_lines = [
            f"GET {path} HTTP/1.1",
            f"Host: {host}",
            "Upgrade: websocket",
            "Connection: Upgrade",
            f"Sec-WebSocket-Key: {key}",
            "Sec-WebSocket-Version: 13",
        ]
        for hk, hv in (extra_headers or {}).items():
            header_lines.append(f"{hk}: {hv}")
        header_lines.append("")
        header_lines.append("")
        writer.write("\r\n".join(header_lines).encode("ascii"))
        await writer.drain()
        status_line = await reader.readline()
        if b"101" not in status_line:
            raise WebSocketTransportError(f"websocket upgrade failed: {status_line!r}")
        while True:
            line = await reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
        self._reader = reader
        self._writer = writer
        self._connected = True
        _ = base64.b64encode(hashlib.sha1((key + _WEBSOCKET_GUID).encode("ascii")).digest()).decode("ascii")
        logger.info("WebSocket transport connected to %s%s", host, path)

    async def send_json(self, payload: dict) -> None:
        import json

        await self.send_text(json.dumps(payload, separators=(",", ":")))

    async def send_text(self, payload: str) -> None:
        if not self._writer:
            raise WebSocketTransportError("transport is not connected")
        frame = _encode_client_text_frame(payload)
        self._writer.write(frame)
        await self._writer.drain()

    async def recv_text(self) -> str | None:
        if not self._reader:
            return None
        while True:
            opcode, payload = await _read_server_frame(self._reader)
            if opcode == 0x8:
                self._connected = False
                return None
            if opcode == 0x9:
                await self._send_pong(payload)
                continue
            if opcode in (0x1, 0x0) and payload:
                return payload.decode("utf-8", errors="replace")

    async def _send_pong(self, payload: bytes) -> None:
        if not self._writer:
            return
        frame = _encode_frame(opcode=0xA, payload=payload, mask=True)
        self._writer.write(frame)
        await self._writer.drain()

    async def close(self) -> None:
        self._connected = False
        if self._writer is None:
            return
        try:
            self._writer.write(_encode_frame(opcode=0x8, payload=b"", mask=True))
            await self._writer.drain()
        except Exception:
            pass
        self._writer.close()
        try:
            await self._writer.wait_closed()
        except Exception:
            pass
        self._reader = None
        self._writer = None


def _encode_client_text_frame(payload: str) -> bytes:
    return _encode_frame(opcode=0x1, payload=payload.encode("utf-8"), mask=True)


def _encode_frame(*, opcode: int, payload: bytes, mask: bool) -> bytes:
    frame = bytearray()
    frame.append(0x80 | (opcode & 0x0F))
    mask_bit = 0x80 if mask else 0x00
    length = len(payload)
    if length < 126:
        frame.append(mask_bit | length)
    elif length < (1 << 16):
        frame.append(mask_bit | 126)
        frame.extend(length.to_bytes(2, "big"))
    else:
        frame.append(mask_bit | 127)
        frame.extend(length.to_bytes(8, "big"))
    if mask:
        masking_key = secrets.token_bytes(4)
        frame.extend(masking_key)
        frame.extend(bytes(b ^ masking_key[i % 4] for i, b in enumerate(payload)))
    else:
        frame.extend(payload)
    return bytes(frame)


async def _read_server_frame(reader: asyncio.StreamReader) -> tuple[int, bytes]:
    header = await reader.readexactly(2)
    opcode = header[0] & 0x0F
    masked = (header[1] & 0x80) != 0
    length = header[1] & 0x7F
    if length == 126:
        length = int.from_bytes(await reader.readexactly(2), "big")
    elif length == 127:
        length = int.from_bytes(await reader.readexactly(8), "big")
    mask_key = await reader.readexactly(4) if masked else b""
    payload = await reader.readexactly(length)
    if masked:
        payload = bytes(b ^ mask_key[i % 4] for i, b in enumerate(payload))
    return opcode, payload
