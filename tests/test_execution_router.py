import pandas as pd

from hibs_racing.cards.refresh_parallel import parallel_map
from hibs_racing.live.execution_router import ExecutionIntent, ExecutionRouter, route_execution_batch


def test_parallel_map_order():
    out = parallel_map([1, 2, 3], lambda x: x * 10, max_workers=2)
    assert out == [10, 20, 30]


def test_execution_router_dry_run_matchbook():
    router = ExecutionRouter()
    intent = ExecutionIntent(
        runner_id="r1:h1",
        race_id="r1",
        horse_name="Horse One",
        course="Chester",
        off_time="2:30",
        stake=2.0,
        bet_type="each_way",
        min_odds=5.0,
        offered_odds=5.0,
        min_place_odds=1.8,
        offered_place_odds=1.8,
        value_flag=True,
        kelly_multiplier=1.0,
        steam_gate="proceed",
        matchbook_runner_id=111,
        matchbook_market_id=222,
        matchbook_place_runner_id=112,
        matchbook_place_market_id=223,
        matchbook_event_id=333,
    )
    legs = router.route_legs(intent)
    assert len(legs) == 2
    assert {leg.payload["bet_leg"] for leg in legs} == {"win", "place"}
    assert all(leg.status == "stub_ok" for leg in legs)
    assert all(leg.payload["stake"] == 1.0 for leg in legs)
    result = router.route(intent)
    assert result.status == "stub_ok"
    assert "Each-way split" in result.message


def test_execution_router_dry_run_matchbook_win_only_legacy():
    router = ExecutionRouter()
    intent = ExecutionIntent(
        runner_id="r1:h1",
        race_id="r1",
        horse_name="Horse One",
        course="Chester",
        off_time="2:30",
        stake=1.0,
        bet_type="win",
        min_odds=5.0,
        offered_odds=5.0,
        value_flag=True,
        kelly_multiplier=1.0,
        steam_gate="proceed",
        matchbook_runner_id=111,
        matchbook_market_id=222,
        matchbook_event_id=333,
    )
    result = router.route(intent)
    assert result.dry_run is True
    assert result.venue == "matchbook"
    assert result.status == "stub_ok"
    assert result.payload["bet_leg"] == "win"


def test_execution_router_rejects_abort_gate():
    router = ExecutionRouter()
    intent = ExecutionIntent(
        runner_id="r1:h1",
        race_id="r1",
        horse_name="Horse One",
        course="Chester",
        off_time="2:30",
        stake=1.0,
        bet_type="each_way",
        min_odds=5.0,
        offered_odds=5.0,
        value_flag=True,
        kelly_multiplier=0.0,
        steam_gate="abort",
        matchbook_runner_id=111,
        matchbook_market_id=222,
        matchbook_event_id=333,
    )
    result = router.route(intent)
    assert result.status == "rejected"
    assert "gate" in result.message.lower()


def test_route_execution_batch_summary():
    intents = [
        ExecutionIntent(
            runner_id="r1:h1",
            race_id="r1",
            horse_name="A",
            course="X",
            off_time="1:00",
            stake=1.0,
            bet_type="each_way",
            min_odds=4.0,
            offered_odds=4.0,
            value_flag=False,
            kelly_multiplier=1.0,
            steam_gate="proceed",
        )
    ]
    report = route_execution_batch(intents)
    assert report["intents"] == 1
    assert report["rejected"] == 1
