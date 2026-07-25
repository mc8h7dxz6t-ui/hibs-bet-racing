from __future__ import annotations

import os
from pathlib import Path

import pytest

from hibs_racing.config import parquet_dir


def test_parquet_dir_honours_hibs_racing_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    data_root = tmp_path / "racing-data"
    monkeypatch.setenv("HIBS_RACING_DATA_DIR", str(data_root))
    out = parquet_dir()
    assert out == data_root / "parquet"
    assert out.is_dir()


def test_parquet_dir_default_under_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HIBS_RACING_DATA_DIR", raising=False)
    out = parquet_dir()
    assert out.name == "parquet"
    assert "data" in out.parts
