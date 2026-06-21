"""Racing institutional evidence gates."""

from __future__ import annotations

from hibs_predictor import racing_evidence as re


def test_racing_evidence_gates_shape(monkeypatch):
    def fake_get(url: str, *, timeout: float = 20.0):
        if url.endswith("/api/ping"):
            return 200, '{"revision":"abc123","ok":true}'
        if url.endswith("/cards"):
            return 200, "<html><body>race card runner jockey</body></html>" * 50
        if "/api/health" in url:
            return 200, '{"telemetry_balance":{"coverage_pct":40},"recon_clean":true,"paper":{"n_rows":30}}'
        if "portfolio" in url:
            return 200, "{}"
        return 404, "not found"

    monkeypatch.setattr(re, "_http_get", fake_get)
    rep = re.racing_evidence_gates()
    assert "gates" in rep
    assert "buyer_ready" in rep
    assert rep["buyer_ready"] is True
    assert rep["evidence_grade"] == "A"


def test_racing_evidence_ping_fail(monkeypatch):
    monkeypatch.setattr(re, "_http_get", lambda url, timeout=20.0: (502, "bad gateway"))
    rep = re.racing_evidence_gates()
    assert rep["buyer_ready"] is False
    assert rep["evidence_grade"] == "D"


def test_racing_evidence_local_base_when_deploy_path_exists(monkeypatch, tmp_path):
    racing = tmp_path / "hibs-racing"
    racing.mkdir()
    monkeypatch.setenv("HIBS_RACING_DEPLOY_PATH", str(racing))
    monkeypatch.delenv("HIBS_RACING_PUBLIC_URL", raising=False)
    monkeypatch.delenv("HIBS_RACING_EVIDENCE_LOCAL", raising=False)
    assert re._racing_base_url() == "http://127.0.0.1:5003"


def test_racing_evidence_public_override(monkeypatch):
    monkeypatch.setenv("HIBS_RACING_PUBLIC_URL", "https://example.com/racing")
    monkeypatch.setenv("HIBS_RACING_EVIDENCE_LOCAL", "0")
    assert re._racing_base_url() == "https://example.com/racing"


def test_racing_evidence_prefers_local_when_deploy_path_exists(monkeypatch, tmp_path):
    racing = tmp_path / "hibs-racing"
    racing.mkdir()
    monkeypatch.setenv("HIBS_RACING_DEPLOY_PATH", str(racing))
    monkeypatch.setenv("HIBS_RACING_PUBLIC_URL", "https://hibs-bet.co.uk/racing")
    monkeypatch.delenv("HIBS_RACING_EVIDENCE_LOCAL", raising=False)
    assert re._racing_base_url() == "http://127.0.0.1:5003"
