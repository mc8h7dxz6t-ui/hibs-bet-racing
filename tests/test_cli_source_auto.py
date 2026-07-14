"""CLI accepts --source auto (daily_refresh.sh / HIBS_RACING_CARD_SOURCE)."""

from __future__ import annotations

import json
from unittest.mock import patch


def test_refresh_cards_cli_accepts_auto_source():
    with patch("hibs_racing.cards.refresh.refresh_cards") as mock_refresh:
        mock_refresh.return_value = {"runners": 12, "paper_recon_clean": True}
        from hibs_racing.cli import main

        rc = main(
            [
                "refresh-cards",
                "--source",
                "auto",
                "--no-window",
                "--regions",
                "gb",
                "--odds-source",
                "none",
            ]
        )
    assert rc == 0
    mock_refresh.assert_called_once()
    assert mock_refresh.call_args.kwargs["source"] == "auto"


def test_refresh_cards_cli_auto_ok_json(capsys):
    with patch("hibs_racing.cards.refresh.refresh_cards") as mock_refresh:
        mock_refresh.return_value = {"runners": 5, "paper_recon_clean": True}
        from hibs_racing.cli import main

        rc = main(["refresh-cards", "--source", "auto", "--no-window", "--odds-source", "none"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["runners"] == 5
