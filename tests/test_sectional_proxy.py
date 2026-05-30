from hibs_racing.nlp.pipeline import parse_comment


def test_canonical_sectional_comment():
    """Elite pitch example: held up → headway 2f out → quickened to lead."""
    f = parse_comment(
        "held up, smooth headway 2f out, quickened to lead inside final furlong"
    )
    labels = f.elite_labels()
    assert labels["LatePaceAcceleration"] == "high"
    assert labels["FinishingBurst"] == "elite"
    assert labels["StaminaDeficit"] is False
    assert f.headway_at_furlongs == 2.0
    assert f.quickened_to_lead is True
    assert f.sectional_composite > 0.5


def test_stamina_deficit_final_furlong():
    f = parse_comment("prominent, faded inside final furlong")
    assert f.StaminaDeficit is True
    assert f.fade_in_final_furlong is True
    assert f.finishing_burst_level == 0


def test_headway_timing_extracted():
    f = parse_comment("in rear, headway 3 furlongs out, kept on well")
    assert f.headway_at_furlongs == 3.0
    assert f.late_pace_level >= 2


def test_as_dict_includes_elite_labels():
    f = parse_comment("smooth headway 2f out, quickened to lead")
    payload = f.as_dict()
    assert payload["elite_labels"]["LatePaceAcceleration"] in ("medium", "high")
    assert payload["elite_labels"]["FinishingBurst"] == "elite"
