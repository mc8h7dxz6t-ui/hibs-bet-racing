"""Provider webhook signature verification — generic, Stripe, Shopify."""

from __future__ import annotations

import base64
import hashlib
import hmac
import time


def verify_provider_signature(
    raw_payload: bytes,
    signature_header: str,
    secret: str,
    *,
    algorithm: str = "sha256",
) -> bool:
    """
    Verify hex HMAC digest (generic ``X-Provider-Signature``).

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


def verify_shopify_hmac(raw_payload: bytes, signature_header: str, secret: str) -> bool:
    """Shopify ``X-Shopify-Hmac-Sha256`` — base64 HMAC-SHA256 of raw body."""
    if not secret or not signature_header:
        return False
    digest = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha256).digest()
    expected = base64.b64encode(digest).decode("ascii")
    return hmac.compare_digest(expected, signature_header.strip())


def verify_stripe_signature(
    raw_payload: bytes,
    signature_header: str,
    secret: str,
    *,
    tolerance_sec: int = 300,
) -> bool:
    """
    Stripe ``Stripe-Signature`` header — ``t=timestamp,v1=hex,...``.

    Uses webhook signing secret (``whsec_...``).
    """
    if not secret or not signature_header:
        return False
    parts: dict[str, list[str]] = {}
    for item in signature_header.split(","):
        if "=" not in item:
            continue
        key, val = item.split("=", 1)
        parts.setdefault(key.strip(), []).append(val.strip())
    timestamps = parts.get("t") or []
    v1_sigs = parts.get("v1") or []
    if not timestamps or not v1_sigs:
        return False
    try:
        ts = int(timestamps[0])
    except ValueError:
        return False
    if abs(int(time.time()) - ts) > tolerance_sec:
        return False
    signed = f"{ts}.".encode("utf-8") + raw_payload
    expected = hmac.new(secret.encode("utf-8"), signed, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, sig) for sig in v1_sigs)


def verify_webhook_signature(
    raw_payload: bytes,
    signature_header: str,
    secret: str,
    *,
    provider: str = "generic",
) -> bool:
    """Dispatch verification by provider id."""
    mode = provider.strip().lower()
    if mode == "shopify":
        return verify_shopify_hmac(raw_payload, signature_header, secret)
    if mode == "stripe":
        return verify_stripe_signature(raw_payload, signature_header, secret)
    return verify_provider_signature(raw_payload, signature_header, secret)
