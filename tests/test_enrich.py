import pandas as pd

from hibs_racing.cards.enrich import merge_null_only
from hibs_racing.cards.form_parser import parse_form_string
from hibs_racing.cards.rp_stats import flatten_runner_stats, parse_horse_stats


def test_parse_horse_stats():
    raw = {"course": {"wins": "2", "runs": "5"}, "distance": {"winsRuns": "0-4"}}
    out = parse_horse_stats(raw)
    assert out["horse_course_wins"] == 2
    assert out["horse_course_runs"] == 5
    assert out["horse_distance_wins"] == 0
    assert out["horse_distance_runs"] == 4


def test_flatten_runner_stats():
    stats = {
        "horse": {"course": {"wins": "1", "runs": "3"}},
        "jockey": {"last14Days": {"winsRuns": "2-10", "strikeRate": 0.2}},
    }
    out = flatten_runner_stats(stats)
    assert out["jockey_rp_14d_wins"] == 2
    assert out["jockey_rp_14d_runs"] == 10


def test_form_parser_cd_bf():
    out = parse_form_string("1CD-2", today_distance_f=8.0)
    assert out["form_cd_flag"] == 1
    assert out["form_lto_position"] == 1


def test_merge_null_only_preserves_spine():
    spine = pd.DataFrame(
        [
            {
                "card_date": "2026-06-01",
                "course": "Newbury",
                "off_time": "14:30",
                "horse_name": "Alpha Star",
                "official_rating": 70,
                "form_string": None,
                "card_comment": "API comment",
                "distance_f": 8.0,
            }
        ]
    )
    enrich = pd.DataFrame(
        [
            {
                "card_date": "2026-06-01",
                "course": "Newbury",
                "off_time": "14:30",
                "horse_name": "Alpha Star",
                "official_rating": 55,
                "form_string": "123-1",
                "card_comment": "RP comment",
                "horse_course_wins": 1,
                "horse_course_runs": 2,
                "distance_f": 8.0,
            }
        ]
    )
    merged = merge_null_only(spine, enrich)
    assert int(merged.iloc[0]["official_rating"]) == 70
    assert merged.iloc[0]["card_comment"] == "API comment"
    assert merged.iloc[0]["form_string"] == "123-1"
    assert merged.iloc[0]["enrich_source"] == "rpscrape"
