import pandas as pd

from hibs_racing.cards.refresh_parallel import parallel_map
from hibs_racing.live.execution_config import EXECUTION_DISABLED_MSG, execution_disabled
from hibs_racing.live.execution_router import ExecutionIntent, ExecutionRouter, route_execution_batch


def test_parallel_map_order():
    out = parallel_map([1, 2, 3], lambda x: x * 10, max_workers=2)
    assert out == [10, 20, 30]


def test_execution_disabled_flag():
    assert execution_disabled() is True


def test_execution_router_returns_disabled():
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
        value_flag=True,
        kelly_multiplier=1.0,
        steam_gate="proceed",
        matchbook_runner_id=111,
        matchbook_market_id=222,
    )
    legs = router.route_legs(intent)
    assert len(legs) == 1
    assert legs[0].status == "disabled"
    assert EXECUTION_DISABLED_MSG in legs[0].message


def test_route_execution_batch_disabled():
    report = route_execution_batch([])
    assert report["status"] == "disabled"
    assert report["results"] == []
