import pandas as pd
from pathlib import Path

from hibs_racing.odds.fractions import fraction_to_decimal
from hibs_racing.odds.matching import horse_names_match, normalize_horse_name
from hibs_racing.odds.oddschecker import _parse_html_table, _row_best_price, fetch_race_odds_page


def test_fraction_to_decimal():
    assert fraction_to_decimal("7/1") == 8.0
    assert fraction_to_decimal("5/2") == 3.5
    assert fraction_to_decimal("evs") == 2.0
    assert fraction_to_decimal("8.0") == 8.0


def test_horse_name_match():
    assert horse_names_match("Star Runner (GB)", "Star Runner")
    assert normalize_horse_name("Hope Rising (IRE)") == "hoperising"


FIXTURE = Path(__file__).parent / "fixtures" / "oddschecker_sample.html"


def test_parse_oddschecker_html():
    html = FIXTURE.read_text(encoding="utf-8")
    df = _parse_html_table(html)
    assert df is not None
    from hibs_racing.odds.oddschecker import _book_columns

    books = _book_columns(df, retail_only=True)
    best, book = _row_best_price(df.iloc[0], books)
    assert best == 9.0
    assert book == "william hill"


def test_fetch_race_odds_page_retail_only(monkeypatch):
    html = FIXTURE.read_text(encoding="utf-8")

    class FakeResp:
        text = html

        def raise_for_status(self):
            return None

    class FakeSession:
        def get(self, url, timeout=45):
            return FakeResp()

    out = fetch_race_odds_page("http://example.com/race", session=FakeSession(), retail_only=True)
    assert len(out) == 2
    star = out[out["horse_name"].str.contains("Star", na=False)].iloc[0]
    assert star["win_decimal"] == 9.0
    assert star["best_book"] == "william hill"


def test_merge_odds_loader_auto_embedded():
    from hibs_racing.odds.loader import resolve_scoring_odds

    cards = pd.DataFrame(
        [
            {"horse_name": "A", "win_decimal": 5.0},
            {"horse_name": "B", "win_decimal": None},
        ]
    )
    odds, meta = resolve_scoring_odds(cards, odds_source="auto")
    assert meta["source"] == "card_embedded"
    assert odds is not None and len(odds) == 1
