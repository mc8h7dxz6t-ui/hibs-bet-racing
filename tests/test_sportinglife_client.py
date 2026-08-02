"""Sporting Life parser tests."""

from hibs_racing.scrapers.sportinglife_client import _parse_fractional_sp, parse_results_from_html


def test_parse_fractional_sp():
    assert _parse_fractional_sp("5/1") == 6.0
    assert _parse_fractional_sp("2.5") == 2.5
    assert _parse_fractional_sp("SP") is None


def test_parse_results_from_html_minimal():
    html = """
    <article data-course="Ascot">
      <span class="horse-name">Fast Horse</span>
      <span class="price">7/2</span>
    </article>
    """
    rows = parse_results_from_html(html, card_date="2026-08-02")
    assert len(rows) == 1
    assert rows[0]["horse_name"] == "Fast Horse"
    assert rows[0]["sp_decimal"] == 4.5
