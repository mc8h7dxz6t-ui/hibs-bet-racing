from hibs_racing.ingest.racing_api import parse_racing_api_payload


def test_parse_racing_api_free_payload():
    payload = {
        "racecards": [
            {
                "course": "Ascot",
                "date": "2026-05-30",
                "off_time": "14:30",
                "race_name": "Handicap",
                "race_class": "Class 4",
                "going": "Good",
                "field_size": "2",
                "region": "GB",
                "runners": [
                    {
                        "horse": "Demo Runner (GB)",
                        "jockey": "H Doyle",
                        "trainer": "T Smith",
                        "draw": "5",
                        "ofr": "72",
                        "last_run": "14",
                    },
                    {
                        "horse": "Favourite (IRE)",
                        "jockey": "R Coakley",
                        "trainer": "A King",
                        "draw": "1",
                        "ofr": "85",
                    },
                ],
            }
        ]
    }
    frame = parse_racing_api_payload(payload, region="gb")
    assert len(frame) == 2
    assert frame.iloc[0]["course"] == "Ascot"
    assert frame.iloc[0]["card_date"] == "2026-05-30"
    assert "runner_id" in frame.columns


def test_parse_racing_api_payload_nan_field_size_uses_runner_count():
    import math

    payload = {
        "racecards": [
            {
                "course": "Ascot",
                "date": "2026-07-29",
                "off_time": "14:30",
                "field_size": math.nan,
                "runners": [
                    {"horse": "A"},
                    {"horse": "B"},
                    {"horse": "C"},
                ],
            }
        ]
    }
    frame = parse_racing_api_payload(payload, region="gb")
    assert len(frame) == 3
    assert int(frame.iloc[0]["field_size"]) == 3


def test_parse_racing_api_payload_uses_fallback_card_date():
    payload = {
        "racecards": [
            {
                "course": "Ascot",
                "off_time": "14:30",
                "runners": [{"horse": "Demo Runner (GB)", "jockey": "H Doyle", "trainer": "T Smith"}],
            }
        ]
    }
    frame = parse_racing_api_payload(payload, region="gb", card_date="2026-07-24")
    assert len(frame) == 1
    assert frame.iloc[0]["card_date"] == "2026-07-24"
