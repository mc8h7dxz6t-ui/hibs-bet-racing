"""Optional HMAC bundle signing for offline auditor trust."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from pathlib import Path
from typing import Any


def signing_key() -> str | None:
    key = os.getenv("INST_BUNDLE_SIGNING_KEY", "").strip()
    return key or None


def sign_bytes(data: bytes, *, key: str | None = None) -> str:
    secret = (key or signing_key() or "").encode("utf-8")
    if not secret:
        raise ValueError("INST_BUNDLE_SIGNING_KEY not set")
    return hmac.new(secret, data, hashlib.sha256).hexdigest()


def write_signature_sidecar(tarball_path: Path, *, bundle_sha256: str, product: str | None = None) -> Path | None:
    key = signing_key()
    if not key:
        return None
    tar_path = Path(tarball_path)
    sig = sign_bytes(tar_path.read_bytes(), key=key)
    payload: dict[str, Any] = {
        "algorithm": "hmac-sha256",
        "bundle_file": tar_path.name,
        "bundle_sha256": bundle_sha256,
        "signature": sig,
        "protocol": "inst-spine-bundle-signature-v1",
    }
    if product:
        payload["product"] = product
    sidecar = tar_path.with_suffix(tar_path.suffix + ".sig.json")
    sidecar.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return sidecar


def verify_signature_sidecar(tarball_path: Path, *, key: str | None = None) -> tuple[bool, str]:
    tar_path = Path(tarball_path)
    sidecar = tar_path.with_suffix(tar_path.suffix + ".sig.json")
    if not sidecar.is_file():
        return True, "no signature sidecar"
    secret = key or signing_key()
    if not secret:
        return False, "signature present but INST_BUNDLE_SIGNING_KEY unset"
    try:
        meta = json.loads(sidecar.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return False, "invalid signature sidecar JSON"
    expected_sig = str(meta.get("signature") or "")
    actual = sign_bytes(tar_path.read_bytes(), key=secret)
    if not hmac.compare_digest(expected_sig, actual):
        return False, "bundle signature mismatch"
    return True, "signature ok"
