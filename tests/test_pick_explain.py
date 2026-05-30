from hibs_racing.pick_explain import explain_pick


def test_explain_pick_combo_and_pace():
    row = {
        "jockey": "H Doyle",
        "trainer": "A King",
        "combo_bayes_place": 0.58,
        "model_place_prob": 0.62,
        "nlp_pace_rank": 1.0,
        "field_size": 10,
        "official_rating": 72,
    }
    out = explain_pick(row)
    assert out["pick_summary"]
    assert len(out["pick_reasons"]) >= 2
    text = " ".join(out["pick_reasons"])
    assert "H Doyle" in text
    assert "pace" in text.lower() or "Harville" in text
