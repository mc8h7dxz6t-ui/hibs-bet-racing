import pytest

from hibs_racing.entity.natural_key import (
    courses_match,
    generate_natural_key,
    normalize_course,
    normalize_off_time,
)


def test_normalize_course_aw():
    assert normalize_course("Newcastle (AW)") == "newcastle"
    assert normalize_course("  Haydock Park  ") == "haydock_park"


def test_normalize_off_time():
    assert normalize_off_time("14:30") == "14:30"
    assert normalize_off_time("2:30pm") == "14:30"
    assert normalize_off_time("14:30:00") == "14:30"


def test_generate_natural_key():
    key = generate_natural_key("2026-05-30", "Newcastle (AW)", "15:30")
    assert key == "2026-05-30_newcastle_15:30"


def test_courses_match_fuzzy():
    assert courses_match("Newcastle", "Newcastle (AW)")
    assert not courses_match("Ascot", "Newcastle")
