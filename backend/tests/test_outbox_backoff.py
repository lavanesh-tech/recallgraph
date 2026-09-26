from recallgraph.events.worker import MAX_BACKOFF_S, backoff_seconds


def test_backoff_is_exponential_and_capped() -> None:
    assert [backoff_seconds(n) for n in (1, 2, 3, 4)] == [30, 60, 120, 240]
    assert backoff_seconds(50) == MAX_BACKOFF_S
