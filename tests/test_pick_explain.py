from hibs_racing.pick_explain import explain_pick
from hibs_racing.web_format import fmt_pct, fmt_prob_phrase, normalize_prob_pct


def test_normalize_prob_pct_fraction_and_percent():
    assert normalize_prob_pct(0.58) == 58.0
    assert normalize_prob_pct(58) == 58.0
    assert normalize_prob_pct(5800) == 58.0
    assert normalize_prob_pct(1000) == 10.0


def test_fmt_pct_handles_double_scaled():
    assert fmt_pct(10) == "10%"
    assert fmt_pct(0.10) == "10%"
    assert fmt_pct(1000) == "10%"


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
    assert len(out["pick_reasons"]) <= 4
    text = " ".join(out["pick_reasons"])
    assert "H Doyle" in text
    assert "1000%" not in text
    assert "58%" in text


def test_explain_pick_accepts_percent_scale_inputs():
    row = {
        "jockey": "A",
        "trainer": "B",
        "combo_bayes_place": 58,
        "model_place_prob": 62,
    }
    out = explain_pick(row)
    text = " ".join(out["pick_reasons"])
    assert "58%" in text
    assert "62%" in text
    assert "5800%" not in text
    assert fmt_prob_phrase(58) == "58%"
