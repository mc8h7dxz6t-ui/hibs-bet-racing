"""Tests for sale gate env overlay."""

from hibs_racing.sale_gates import apply_sale_gate_overrides, sale_gates_enabled


def test_sale_gates_off_by_default(monkeypatch):
    monkeypatch.delenv("HIBS_RACING_SALE_GATES", raising=False)
    assert sale_gates_enabled() is False
    out = apply_sale_gate_overrides({"min_place_ev": 0.05})
    assert out["min_place_ev"] == 0.05
    assert "_sale_gates_active" not in out


def test_sale_gates_tighten_thresholds(monkeypatch):
    monkeypatch.setenv("HIBS_RACING_SALE_GATES", "1")
    out = apply_sale_gate_overrides({"min_place_ev": 0.05, "min_combo_bayes_place": 0.22})
    assert out["min_place_ev"] == 0.12
    assert out["min_combo_bayes_place"] == 0.28
    assert out["_sale_gates_active"] is True
