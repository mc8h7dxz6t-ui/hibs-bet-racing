import pandas as pd

from hibs_racing.cards.score_card import score_upcoming_cards
from hibs_racing.place.harville import harville_place_probs


def test_harville_place_probs_sum():
    wp = [0.4, 0.3, 0.2, 0.1]
    pp = harville_place_probs(wp, places=3)
    assert len(pp) == 4
    assert all(0 <= p <= 1 for p in pp)


def test_harville_longshot_discount_reduces_tail_place_prob():
    wp = [0.02, 0.02, 0.46, 0.50]
    plain = harville_place_probs(wp, places=3, longshot_discount=1.0)
    discounted = harville_place_probs(wp, places=3, longshot_discount=0.85, longshot_win_prob_threshold=0.03)
    assert discounted[0] < plain[0]
    assert discounted[1] < plain[1]


def test_score_card_smoke(monkeypatch, tmp_path):
    from hibs_racing.config import load_config
    from hibs_racing.features.store import connect, init_db

    cfg = load_config()
    db = tmp_path / "t.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)

    cards = pd.DataFrame(
        [
            {
                "runner_id": "R1:horse_a",
                "race_id": "R1",
                "card_date": "2026-05-30",
                "horse_id": "Horse A",
                "horse_name": "Horse A",
                "jockey": "J1",
                "trainer": "T1",
                "official_rating": 70,
                "rpr": 75,
                "race_class": "Class 4",
                "field_size": 2,
                "card_comment": "held up, headway 2f out",
            },
            {
                "runner_id": "R1:horse_b",
                "race_id": "R1",
                "card_date": "2026-05-30",
                "horse_id": "Horse B",
                "horse_name": "Horse B",
                "jockey": "J2",
                "trainer": "T2",
                "official_rating": 80,
                "rpr": 82,
                "race_class": "Class 4",
                "field_size": 2,
                "card_comment": "",
            },
        ]
    )
    scored = score_upcoming_cards(cards, database=db)
    assert len(scored) == 2
    assert "model_place_prob" in scored.columns
