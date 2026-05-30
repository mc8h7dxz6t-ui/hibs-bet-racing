import pandas as pd
import pytest

from hibs_racing.ingest.rpscrape_adapter import normalize_rpscrape_csv


@pytest.fixture()
def mini_rpscrape_csv(tmp_path):
    path = tmp_path / "rp.csv"
    pd.DataFrame(
        [
            {
                "date": "2024-05-15",
                "region": "GB",
                "course": "Bath",
                "off": "20:40",
                "race_name": "Test Handicap",
                "type": "Flat",
                "dist_f": "10f",
                "going": "Good",
                "ran": 13,
                "pos": 2,
                "horse": "Snapcracklepop (GB)",
                "dec": 4.5,
                "comment": "In touch with leaders - headway from over 2f out - kept on inside final furlong",
            }
        ]
    ).to_csv(path, index=False)
    return path


def test_normalize_rpscrape_csv(mini_rpscrape_csv, tmp_path):
    out = normalize_rpscrape_csv(mini_rpscrape_csv, output=tmp_path / "hibs.csv")
    frame = pd.read_csv(out)
    assert len(frame) == 1
    assert frame.iloc[0]["finish_pos"] == 2
    assert frame.iloc[0]["distance_f"] == 10.0
    assert "headway" in frame.iloc[0]["comment"].lower()
