"""Constant-time HMAC verification for inbound provider webhooks."""

from __future__ import annotations

import hashlib
import hmac


def verify_provider_signature(
    raw_payload: bytes,
    signature_header: str,
    secret: str,
    *,
    algorithm: str = "sha256",
) -> bool:
    """
    Verify ``X-Provider-Signature`` (hex digest) against ``secret``.

    Returns False on missing secret, empty signature, or mismatch.
    """
    if not secret or not signature_header:
        return False
    try:
        expected = hmac.new(
            secret.encode("utf-8"),
            raw_payload,
            getattr(hashlib, algorithm),
        ).hexdigest()
    except (AttributeError, TypeError):
        return False
    return hmac.compare_digest(expected, signature_header.strip())
