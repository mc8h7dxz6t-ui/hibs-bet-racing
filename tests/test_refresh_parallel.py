from hibs_racing.cards.refresh_parallel import parallel_map, timed_ms


def test_timed_ms():
    out, ms = timed_ms(lambda: 42)
    assert out == 42
    assert ms >= 0
