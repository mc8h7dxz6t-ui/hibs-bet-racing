"""Football-Data.co.uk CSV closing-line matrices — training baseline seed."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterator, List, Mapping, Optional

from hibs_predictor.ingress.schema_guard import IngressRejectError
from hibs_predictor.price_truth import triplet_from_mapping

# Standard Football-Data.co.uk columns (E0.csv, SP1.csv, …)
_CLOSING_COLS = {
    "home": ("B365H", "BWH", "PSH", "PH", "MaxH", "AvgH"),
    "draw": ("B365D", "BWD", "PSD", "PD", "MaxD", "AvgD"),
    "away": ("B365A", "BWA", "PSA", "PA", "MaxA", "AvgA"),
}


@dataclass(frozen=True)
class ClosingLineRow:
    division: str
    date: str
    home_team: str
    away_team: str
    ftr: str
    closing_1x2: Dict[str, float]
    source_file: str

    def to_price_truth_seed(self) -> Dict[str, Any]:
        triplet = triplet_from_mapping(self.closing_1x2)
        return {
            "fixture_key": f"{self.date}|{self.home_team}|{self.away_team}",
            "closing_odds_1x2": triplet,
            "price_truth": {
                "baseline_source": "football_data_co_uk_csv",
                "division": self.division,
                "result": self.ftr,
            },
        }


def _first_valid_odds(row: Mapping[str, str], candidates: tuple[str, ...]) -> Optional[float]:
    for col in candidates:
        raw = row.get(col)
        if raw is None or str(raw).strip() == "":
            continue
        try:
            v = float(raw)
        except (TypeError, ValueError):
            continue
        if v > 1.0:
            return v
    return None


def parse_football_data_csv(path: Path) -> Iterator[ClosingLineRow]:
    """Parse one Football-Data.co.uk results file into closing-line seeds."""
    if not path.is_file():
        raise FileNotFoundError(path)
    with path.open(newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        if not reader.fieldnames:
            raise IngressRejectError(f"empty CSV header: {path}")
        for i, row in enumerate(reader, start=2):
            if not row:
                continue
            div = str(row.get("Div") or row.get("div") or "").strip()
            date = str(row.get("Date") or "").strip()
            home = str(row.get("HomeTeam") or "").strip()
            away = str(row.get("AwayTeam") or "").strip()
            if not all([div, date, home, away]):
                raise IngressRejectError(f"structural null row {path}:{i}")
            closing: Dict[str, float] = {}
            for side, cols in _CLOSING_COLS.items():
                price = _first_valid_odds(row, cols)
                if price is None:
                    raise IngressRejectError(f"missing closing odds {side} at {path}:{i}")
                closing[side] = price
            yield ClosingLineRow(
                division=div,
                date=date,
                home_team=home,
                away_team=away,
                ftr=str(row.get("FTR") or "").strip(),
                closing_1x2=closing,
                source_file=path.name,
            )


def load_baseline_matrix(directory: Path, *, limit: Optional[int] = None) -> List[Dict[str, Any]]:
    """Load all *.csv matrices under directory as price_truth training seeds."""
    seeds: List[Dict[str, Any]] = []
    for path in sorted(directory.glob("*.csv")):
        for row in parse_football_data_csv(path):
            seeds.append(row.to_price_truth_seed())
            if limit and len(seeds) >= limit:
                return seeds
    return seeds
