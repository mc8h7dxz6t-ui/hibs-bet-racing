from hibs_racing.web_service import attach_deep_links_to_picks, resolve_race_deep_link


def test_resolve_race_deep_link_by_race_id():
    meetings = [
        {
            "slug": "1-chester-2026-05-30",
            "races": [{"race_id": "919046", "race_slug": "r2"}],
        }
    ]
    link = resolve_race_deep_link(meetings, race_id="919046")
    assert link["meeting"] == "1-chester-2026-05-30"
    assert link["race"] == "race-1-chester-2026-05-30-r2"
    assert link["race_id"] == "919046"


def test_resolve_race_deep_link_explicit():
    meetings = []
    link = resolve_race_deep_link(meetings, meeting="1-ascot", race="r3")
    assert link["meeting"] == "1-ascot"
    assert link["race"] == "race-1-ascot-r3"


def test_attach_deep_links_to_picks():
    meetings = [
        {
            "slug": "1-york-2026-05-31",
            "races": [{"race_id": "R99", "race_slug": "r1"}],
        }
    ]
    picks = [{"race_id": "R99", "runner_id": "R99:horse_a", "horse_name": "Horse A"}]
    out = attach_deep_links_to_picks(picks, meetings)
    assert out[0]["deep_link"]["meeting"] == "1-york-2026-05-31"
    assert out[0]["deep_link"]["runner_id"] == "R99:horse_a"
