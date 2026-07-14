"""Bundle HMAC signing — Wave 4."""

from __future__ import annotations

from pathlib import Path

import pytest

from inst_spine.bundle_sign import sign_bytes, verify_signature_sidecar, write_signature_sidecar
from inst_spine.export import build_audit_bundle
from inst_spine.ledger import AppendOnlyLedger


def test_bundle_sign_and_verify(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("INST_BUNDLE_SIGNING_KEY", "test-signing-secret")
    db = tmp_path / "sign.sqlite"
    ledger = AppendOnlyLedger(db)
    ledger.append(event_type="decision", payload={"x": 1}, manifest_id="s1")
    tar = tmp_path / "signed.tar"
    result = build_audit_bundle(db, tarball_path=tar, product="sign-test")
    assert result.ok
    sidecar = tar.with_suffix(tar.suffix + ".sig.json")
    assert sidecar.is_file()
    ok, msg = verify_signature_sidecar(tar)
    assert ok is True, msg

    tampered = tar.read_bytes() + b"x"
    tar.write_bytes(tampered)
    ok2, msg2 = verify_signature_sidecar(tar)
    assert ok2 is False
    assert "mismatch" in msg2


def test_sign_bytes_requires_key():
    with pytest.raises(ValueError, match="INST_BUNDLE_SIGNING_KEY"):
        sign_bytes(b"data", key="")
