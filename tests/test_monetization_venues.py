"""Extended monetization venue tests."""

from hibs_racing.utils.monetization import (
    active_venues,
    attach_monetized_links,
    default_affiliate_venue,
    generate_monetized_link,
    public_monetization_payload,
    routing_channels,
)


def test_default_affiliate_venue_is_matchbook(monkeypatch):
    for key in ("HIBS_AFFILIATE_VENUE", "HIBS_BETFAIR_MONETIZATION_ENABLED"):
        monkeypatch.delenv(key, raising=False)
    assert default_affiliate_venue() == "matchbook"


def test_betfair_requires_enable_flag_and_credentials(monkeypatch):
    monkeypatch.delenv("HIBS_BETFAIR_MONETIZATION_ENABLED", raising=False)
    monkeypatch.setenv("BETFAIR_APP_KEY", "k")
    monkeypatch.setenv("BETFAIR_USERNAME", "u")
    monkeypatch.setenv("BETFAIR_PASSWORD", "p")
    assert "betfair" not in active_venues()
    monkeypatch.setenv("HIBS_BETFAIR_MONETIZATION_ENABLED", "1")
    assert "betfair" in active_venues()


def test_routing_channels_matchbook_first(monkeypatch):
    monkeypatch.delenv("HIBS_BETFAIR_MONETIZATION_ENABLED", raising=False)
    channels = routing_channels()
    assert channels[0] == "matchbook"
    assert "smarkets" in channels


def test_public_payload_lists_venues(monkeypatch):
    monkeypatch.delenv("HIBS_BETFAIR_MONETIZATION_ENABLED", raising=False)
    payload = public_monetization_payload()
    assert payload["monetization_primary_venue"] == "matchbook"
    assert "matchbook" in payload["monetization_active_venues"]


def test_generate_monetized_link_uses_query_string(monkeypatch, tmp_path):
    from hibs_racing.utils import ui_settings as mod

    monkeypatch.setattr(mod, "SETTINGS_PATH", tmp_path / "empty.json")
    for key in (
        "HIBS_AFFILIATE_VENUE",
        "HIBS_AFFILIATE_UTM_SOURCE",
        "HIBS_AFFILIATE_TRACKING_ID",
        "AFFILIATE_MATCHBOOK_BASE_URL",
        "AFFILIATE_BETFAIR_BASE_URL",
    ):
        monkeypatch.delenv(key, raising=False)
    url = generate_monetized_link("Golden Fleece", "Epsom", "14:30", venue="matchbook")
    assert url.startswith("https://www.matchbook.com?")
    assert "utm_source=hibs_racing_app" in url


def test_attach_monetized_links_includes_venue():
    picks = [{"horse_name": "A", "course": "York", "off_time": "15:00"}]
    out = attach_monetized_links(picks)
    assert out[0]["monetized_link"].startswith("https://")
    assert out[0]["monetization_venue"] == "matchbook"
