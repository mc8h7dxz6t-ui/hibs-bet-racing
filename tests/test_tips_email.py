import email
from email import policy
from pathlib import Path

import pytest

from hibs_racing.features.store import connect, init_db
from hibs_racing.tips.email_load import load_eml
from hibs_racing.tips.ingest import ingest_email_file
from hibs_racing.tips.parse_body import parse_odds, parse_tips_from_text


FIXTURE = Path(__file__).parent / "fixtures" / "tip_email_sample.eml"


def test_load_eml_extracts_body():
    loaded = load_eml(FIXTURE)
    assert "Storm Spirit" in loaded.body_text
    assert loaded.card_date == "2025-05-24"
    assert loaded.message_id


def test_parse_odds_fractional():
    q, d = parse_odds("5/1 each way")
    assert q == "5/1"
    assert d == 6.0


def test_parse_tips_from_sample_body():
    loaded = load_eml(FIXTURE)
    tips = parse_tips_from_text(loaded.body_text, default_card_date=loaded.card_date)
    horses = {t.horse_name for t in tips if t.horse_name}
    assert "Storm Spirit" in horses
    assert any(t.stable_intel == "yes" for t in tips)
    assert any(t.course == "Chester" for t in tips)


def test_ingest_tips_to_db(tmp_path, monkeypatch):
    db = tmp_path / "tips.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)

    with connect(db) as conn:
        conn.execute(
            """
            INSERT INTO upcoming_runners (
                runner_id, race_id, card_date, off_time, course, horse_id, horse_name,
                source, fetched_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "R1:storm_spirit",
                "R1",
                "2025-05-24",
                "14:30",
                "Chester",
                "h1",
                "Storm Spirit",
                "test",
                "now",
            ),
        )
        conn.commit()

    result = ingest_email_file(FIXTURE, database=db, match=True)
    assert result["inserted"] >= 2
    assert result["matched"] >= 1

    with connect(db) as conn:
        rows = conn.execute("SELECT COUNT(*) FROM tipster_tips").fetchone()[0]
    assert rows >= 2


def test_split_paste_multiple_emails():
    from hibs_racing.tips.email_load import load_pasted_text, split_paste_chunks

    blob = """From: a@b.com
Subject: Tips one
Date: Sat, 24 May 2025 08:00:00 +0100

NAP: Alpha (Chester, 2:30) 5/1

---

From: a@b.com
Subject: Tips two
Date: Sun, 25 May 2025 08:00:00 +0100

NB: Beta (York, 3:00) 4/1
"""
    chunks = split_paste_chunks(blob)
    assert len(chunks) >= 2
    loaded = load_pasted_text(blob)
    assert len(loaded) >= 2


def test_ingest_body_only_paste(tmp_path, monkeypatch):
    from hibs_racing.tips.ingest import ingest_pasted_text

    db = tmp_path / "tips.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    text = "NAP: Storm Spirit (Chester, 2:30) 5/1 each way\nStable word on this."
    result = ingest_pasted_text(text, database=db, default_date="2025-05-24", match=False)
    assert result["inserted"] >= 1


REAL_TIPSTER_PASTE = """
2.00 Carlisle REALIGN 11/2 1pt win

2.33 Carlisle WASHINGTON HEIGHTS 9/2 1pt win NAP

3.30 Chester PALMAR BAY 6/1 1pt win NB

0.25pt Win Trixie

3.45 Carlisle ARCHER ROYAL 20/1 0.75pt ew 5 places (Paddy Power, Betfair & SkyBet)(16/1 365)

4.00 Beverley HAVANA BLUE 11/1 0.75pt ew

0.5pt Each Way Double

Afraid there will be no reviews for tomorrows selections, rest assured that the same work has gone into them. Good Luck
"""


def test_friday_reviews_with_prose():
    from pathlib import Path

    text = Path(__file__).parent.joinpath("fixtures", "tipster_friday_reviews.txt").read_text()
    tips = parse_tips_from_text(text, default_card_date="2026-06-06")
    assert len(tips) == 2
    by_horse = {t.horse_name: t for t in tips}
    assert by_horse["Midnight Lir"].off_time == "15:10"
    assert by_horse["Gallant Lion"].off_time == "15:20"
    assert by_horse["Midnight Lir"].review_text and "handicapped" in by_horse["Midnight Lir"].review_text.lower()
    assert by_horse["Gallant Lion"].review_text and "Jason Watson" in by_horse["Gallant Lion"].review_text
    assert by_horse["Midnight Lir"].stable_intel == "no"


def test_real_tipster_schedule_format():
    tips = parse_tips_from_text(REAL_TIPSTER_PASTE.strip(), default_card_date="2026-05-31")
    assert len(tips) == 5
    by_horse = {t.horse_name: t for t in tips}
    assert by_horse["Realign"].course == "Carlisle"
    assert by_horse["Realign"].off_time == "14:00"
    assert by_horse["Realign"].odds_quoted == "11/2"
    assert by_horse["Washington Heights"].confidence == "NAP"
    assert by_horse["Washington Heights"].bet_type == "nap"
    assert by_horse["Palmar Bay"].confidence == "NB"
    assert by_horse["Palmar Bay"].course == "Chester"
    assert by_horse["Archer Royal"].bet_type == "each_way"
    assert by_horse["Archer Royal"].odds_quoted == "20/1"
    assert by_horse["Havana Blue"].course == "Beverley"


def test_ingest_dedup(tmp_path, monkeypatch):
    db = tmp_path / "tips.sqlite"
    monkeypatch.setenv("HIBS_RACING_DB_PATH", str(db))
    init_db(db)
    first = ingest_email_file(FIXTURE, database=db, match=False)
    second = ingest_email_file(FIXTURE, database=db, match=False)
    assert first["inserted"] >= 1
    assert second["skipped_duplicate"] >= first["inserted"]
