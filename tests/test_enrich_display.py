from hibs_racing.cards.enrich_display import build_enrich_display, format_gate_reason


def test_build_enrich_display():
    out = build_enrich_display(
        {
            "horse_course_wins": 2,
            "horse_course_runs": 5,
            "horse_distance_wins": 0,
            "horse_distance_runs": 4,
            "form_cd_flag": 1,
            "form_trip_change_f": 2.0,
            "trainer_rtf": 18.5,
            "jockey_rp_14d_wins": 3,
            "jockey_rp_14d_runs": 12,
            "enrich_source": "rpscrape",
            "value_gate_reason": "poor_distance_record",
        }
    )
    assert len(out["enrich_fit_rows"]) == 2
    assert out["enrich_fit_rows"][0]["label"] == "At this course"
    assert "2 wins from 5 runs" in out["enrich_fit_rows"][0]["value"]
    assert out["enrich_flags"][0]["code"] == "CD"
    assert out["enrich_trip_label"] == "Up 2f in trip vs last run"
    assert out["enrich_has_data"] is True
    assert "RTF" in (out["enrich_rtf_label"] or "")
    assert out["value_gate_label"] == "Poor distance record"


def test_build_enrich_display_empty():
    out = build_enrich_display({})
    assert out["enrich_has_data"] is False
    assert out["enrich_fit_line"] is None


def test_format_gate_reason():
    assert format_gate_reason("cold_trainer") == "Cold trainer RTF"
    assert format_gate_reason("unknown_code") == "Unknown code"
