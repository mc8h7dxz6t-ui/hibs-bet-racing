from hibs_racing.ingest.rate_limit import pause_sec, rate_limits, rp_verdict_workers


def test_rate_limits_defaults():
    limits = rate_limits()
    assert limits["racing_api_pause_sec"] >= 1.0
    assert rp_verdict_workers() <= 4
    assert pause_sec("rp_scrape_day_pause_sec") >= 2.0


def test_env_override(monkeypatch):
    monkeypatch.setenv("RP_VERDICT_WORKERS", "1")
    assert rp_verdict_workers() == 1
