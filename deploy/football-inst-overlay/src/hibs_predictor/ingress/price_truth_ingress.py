"""Map external sharp feeds into internal bookmaker panel + price_truth shapes."""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

from hibs_predictor.ingress.schema_guard import IngressRejectError, validate_ingress_payload
from hibs_predictor.price_truth import triplet_from_mapping

SHARP_BOOK_ALIASES = {
    "pinnacle": "Pinnacle",
    "singbet": "Singbet",
    "sing bet": "Singbet",
    "betfair": "Betfair Exchange",
    "betfair exchange": "Betfair Exchange",
    "betfair_ex": "Betfair Exchange",
}

_OUTCOME_ALIASES = {
    "home": "home",
    "1": "home",
    "h": "home",
    "draw": "draw",
    "x": "draw",
    "d": "draw",
    "away": "away",
    "2": "away",
    "a": "away",
}


def _norm_book(name: str) -> Optional[str]:
    key = (name or "").strip().lower().replace("_", " ")
    if key in SHARP_BOOK_ALIASES:
        return SHARP_BOOK_ALIASES[key]
    for token, canonical in SHARP_BOOK_ALIASES.items():
        if token in key:
            return canonical
    return None


def _norm_side(raw: str) -> Optional[str]:
    return _OUTCOME_ALIASES.get((raw or "").strip().lower())


def oddspapi_event_to_bookmaker_panel(event: Mapping[str, Any]) -> List[Dict[str, Any]]:
    """
    Convert one OddsPapi event into `all_bookmaker_odds` rows.

    Expected shape (schema 1.0.x):
      schema_version, event_id, bookmakers[{name, markets[{key:h2h, outcomes[{name, price}]}]}]
    """
    validate_ingress_payload(
        event,
        expected_min="1.0.0",
        expected_max="1.99.99",
        required_paths=("event_id", "bookmakers"),
    )
    rows: List[Dict[str, Any]] = []
    for bm in event.get("bookmakers") or []:
        if not isinstance(bm, Mapping):
            raise IngressRejectError("bookmaker row must be mapping")
        canonical = _norm_book(str(bm.get("name") or bm.get("bookmaker") or ""))
        if not canonical:
            continue
        triplet: Dict[str, Optional[float]] = {"home": None, "draw": None, "away": None}
        for market in bm.get("markets") or []:
            if not isinstance(market, Mapping):
                continue
            key = str(market.get("key") or market.get("market") or "").lower()
            if key not in ("h2h", "1x2", "match_odds", "match_winner"):
                continue
            for out in market.get("outcomes") or []:
                if not isinstance(out, Mapping):
                    continue
                side = _norm_side(str(out.get("name") or out.get("outcome") or ""))
                if not side:
                    continue
                try:
                    price = float(out.get("price") or out.get("odds"))
                except (TypeError, ValueError):
                    raise IngressRejectError(f"invalid price for {canonical}/{side}")
                if price <= 1.0:
                    raise IngressRejectError(f"non-decimal odds {price} for {canonical}/{side}")
                triplet[side] = price
        if any(v is None for v in triplet.values()):
            raise IngressRejectError(f"incomplete 1X2 triplet for sharp book {canonical}")
        rows.append(
            {
                "bookmaker": canonical,
                "source": "oddspapi",
                "home": triplet["home"],
                "draw": triplet["draw"],
                "away": triplet["away"],
            }
        )
    if not rows:
        raise IngressRejectError("no sharp book rows after filter (Pinnacle/Singbet/Betfair)")
    return rows


def panel_to_price_truth_seed(panel: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Minimal price_truth block for downstream enrich_clv_price_truth."""
    from hibs_predictor.data_aggregator import compute_best_line_from_bookmakers

    line_shop = compute_best_line_from_bookmakers(panel)
    best = line_shop.get("best_odds_1x2") or {}
    return {
        "opening_odds_1x2": triplet_from_mapping(best),
        "price_truth": {
            "ingress_source": "oddspapi",
            "sharp_anchor_implied": line_shop.get("sharp_anchor_implied") or {},
            "bookmaker_panel_n": len(panel),
        },
    }
