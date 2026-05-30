from hibs_racing.nlp.normalize import normalize_comment
from hibs_racing.nlp.tagger_regex import tag_comment


def test_normalize_expands_furlong_shorthand():
    norm = normalize_comment("Held up, headway 2f out, quickened")
    assert "2 furlongs" in norm.normalized
    assert "held up" in norm.normalized


def test_late_pace_and_finishing_burst():
    tags = tag_comment("held up, smooth headway 2f out, quickened to lead inside final furlong")
    assert tags.late_pace_acceleration > 0
    assert tags.finishing_burst > 0
    assert tags.held_up > 0
    assert tags.tag_count >= 3


def test_stamina_deficit():
    tags = tag_comment("prominent, weakened inside final furlong")
    assert tags.stamina_deficit > 0
    assert tags.prominent_early > 0


def test_trouble_in_running():
    tags = tag_comment("hampered early, short of room 2f out")
    assert tags.trouble_in_running > 0
