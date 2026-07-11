from hibs_predictor.web_format import fmt_pct, fmt_prob, fmt_roi


def test_fmt_prob_decimal():
    assert fmt_prob(42.34) == "42.3%"
    assert fmt_prob(0.42) == "42.0%"


def test_fmt_roi_positive():
    assert fmt_roi(12.34) == "+12.3%"
    assert fmt_roi(0) == "0.0%"


def test_fmt_roi_negative():
    assert fmt_roi(-5.5) == "-5.5%"


def test_fmt_pct_fraction():
    assert fmt_pct(0.25) == "25%"
