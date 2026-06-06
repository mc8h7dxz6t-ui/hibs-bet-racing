from hibs_racing.institutional.telemetry_balance import evaluate_telemetry_balance


def _sample_refresh():
    return {
        "manifest_id": "abc123",
        "card_dates": ["2026-06-04"],
        "runners": 400,
        "odds_runners": 380,
        "odds_source": "matchbook",
        "timings_ms": {
            "fetch_ms": 2000.0,
            "odds_ms": 400.0,
            "score_ms": 15000.0,
            "total_ms": 17500.0,
        },
        "exchange_audit": {
            "coverage_ratio": 0.95,
            "runners_priced": 380,
            "errors": [],
        },
    }


def test_telemetry_balance_passes_balanced_refresh():
    report = evaluate_telemetry_balance(refresh_payload=_sample_refresh())
    assert report.passed is True
    assert report.matchbook_coverage_ratio == 0.95
    assert report.shares_pct["fetch_ms"] > 0
    assert report.shares_pct["odds_ms"] > 0


def test_telemetry_balance_fails_low_coverage():
    payload = _sample_refresh()
    payload["exchange_audit"]["coverage_ratio"] = 0.10
    report = evaluate_telemetry_balance(refresh_payload=payload)
    assert report.passed is False
    names = {c["name"] for c in report.checks if not c["passed"]}
    assert "matchbook_coverage" in names


def test_observation_lane_softer_coverage():
    payload = _sample_refresh()
    payload["exchange_audit"]["coverage_ratio"] = 0.40
    prod = evaluate_telemetry_balance(refresh_payload=payload, observation_lane=False)
    obs = evaluate_telemetry_balance(refresh_payload=payload, observation_lane=True)
    assert prod.passed is False
    assert obs.passed is True
