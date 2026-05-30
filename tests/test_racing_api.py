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
    assert "runner_id" in frame.columns
