from hibs_racing.ingest.scrape import normalize_rps_race_type


def test_normalize_rps_race_type_jump_alias():
    assert normalize_rps_race_type("jump") == "jumps"
    assert normalize_rps_race_type("jumps") == "jumps"
    assert normalize_rps_race_type("flat") == "flat"
    assert normalize_rps_race_type("FLAT") == "flat"
