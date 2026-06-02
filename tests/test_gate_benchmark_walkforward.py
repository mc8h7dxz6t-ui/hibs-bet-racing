from datetime import date

from hibs_racing.backtest.gate_benchmark import _month_periods


def test_month_periods_spans_partial_months():
    periods = _month_periods(date(2026, 3, 15), date(2026, 5, 10))
    labels = [p[0] for p in periods]
    assert labels == ["2026-03", "2026-04", "2026-05"]
    assert periods[0][1] == "2026-03-15"
    assert periods[0][2] == "2026-03-31"
    assert periods[-1][2] == "2026-05-10"
