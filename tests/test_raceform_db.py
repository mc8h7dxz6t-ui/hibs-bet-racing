from hibs_racing.ingest.raceform_db import fractional_to_decimal, normalize_raceform_frame


def test_fractional_to_decimal():
    assert abs(fractional_to_decimal("5/1") - 6.0) < 0.01
    assert abs(fractional_to_decimal("1/3F") - (1 + 1 / 3)) < 0.01
    assert fractional_to_decimal("") is None


def test_normalize_raceform_minimal():
    import pandas as pd

    frame = pd.DataFrame(
        [
            {
                "date": "2026-01-01",
                "course": "Ascot",
                "race_id": "123",
                "off": "14:00",
                "race_name": "Handicap",
                "type": "Flat",
                "class": "Class 4",
                "going": "Good",
                "ran": 10,
                "pos": 2,
                "draw": 5,
                "horse": "Test Horse (GB)",
                "jockey": "J Bloggs",
                "trainer": "T Smith",
                "sp": "4/1",
                "or": 72,
                "rpr": 78,
                "comment": "held up, headway 2f out, ran on well",
            }
        ]
    )
    out = normalize_raceform_frame(frame)
    assert len(out) == 1
    assert out.iloc[0]["official_rating"] == 72
    assert abs(out.iloc[0]["sp_decimal"] - 5.0) < 0.01
