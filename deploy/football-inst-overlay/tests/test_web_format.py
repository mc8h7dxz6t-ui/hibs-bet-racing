from hibs_predictor.web_format import fmt_pct, fmt_roi


def test_fmt_roi_positive():
    assert fmt_roi(12.34) == "+12.3%"
    assert fmt_roi(0) == "0.0%"


def test_fmt_roi_negative():
    assert fmt_roi(-5.5) == "-5.5%"


def test_fmt_pct_fraction():
    assert fmt_pct(0.25) == "25%"
