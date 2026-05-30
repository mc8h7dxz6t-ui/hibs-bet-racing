import pytest


def test_refresh_cards_cli_registered():
    from hibs_racing.cli import cmd_refresh_cards

    assert callable(cmd_refresh_cards)


def test_ingest_raceform_sync_flag_in_parser():
    import argparse
    from hibs_racing.cli import cmd_ingest_raceform

    assert callable(cmd_ingest_raceform)
