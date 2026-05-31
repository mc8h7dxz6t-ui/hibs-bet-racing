from hibs_racing.utils.monetization import (
    attach_monetized_links,
    generate_monetized_link,
)


def test_generate_monetized_link_uses_query_string():
    url = generate_monetized_link("Golden Fleece", "Epsom", "14:30", venue="matchbook")
    assert url.startswith("https://www.matchbook.com?")
    assert "utm_source=hibs_racing_app" in url
    assert "selection=Golden+Fleece" in url or "selection=Golden%20Fleece" in url
    assert "event_ref=epsom_14%3A30" in url or "event_ref=epsom_14:30" in url


def test_attach_monetized_links():
    picks = [{"horse_name": "A", "course": "York", "off_time": "15:00"}]
    out = attach_monetized_links(picks)
    assert out[0]["monetized_link"].startswith("https://")


def test_novice_candidates_include_monetized_link():
    from hibs_racing.web_service import novice_pick_candidates

    meetings = [
        {
            "course": "York",
            "slug": "1-york",
            "races": [
                {
                    "race_slug": "r1",
                    "off_time": "15:30",
                    "runners": [
                        {
                            "runner_id": "x:1",
                            "horse_name": "Blue Sonic",
                            "win_decimal": 6.0,
                            "model_place_prob": 0.4,
                            "value_flag": 1,
                            "market_gauge": {"gate": "proceed"},
                        }
                    ],
                }
            ],
        }
    ]
    out = novice_pick_candidates(meetings)
    assert "monetized_link" in out[0]
    assert "utm_source=hibs_racing_app" in out[0]["monetized_link"]
