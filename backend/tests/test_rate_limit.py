from app.services.rate_limit import SlidingWindowLimiter


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_allows_up_to_the_limit_then_refuses() -> None:
    limiter = SlidingWindowLimiter(3, 60, FakeClock())
    assert [limiter.hit("a") for _ in range(4)] == [True, True, True, False]


def test_keys_are_limited_independently() -> None:
    limiter = SlidingWindowLimiter(1, 60, FakeClock())
    assert limiter.hit("a")
    assert limiter.hit("b")
    assert not limiter.hit("a")


def test_window_slides() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(2, 60, clock)
    assert limiter.hit("a")
    clock.now += 30
    assert limiter.hit("a")
    assert not limiter.hit("a")
    clock.now += 31  # the first hit has aged out, the second hasn't
    assert limiter.hit("a")
    assert not limiter.hit("a")


def test_refused_hits_do_not_count() -> None:
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, 60, clock)
    assert limiter.hit("a")
    for _ in range(5):
        assert not limiter.hit("a")
    clock.now += 61
    assert limiter.hit("a")


def test_zero_limit_disables_it() -> None:
    limiter = SlidingWindowLimiter(0, 60, FakeClock())
    assert all(limiter.hit("a") for _ in range(100))


def test_stale_keys_are_swept_once_there_are_many(monkeypatch) -> None:
    monkeypatch.setattr(SlidingWindowLimiter, "_SWEEP_THRESHOLD", 5)
    clock = FakeClock()
    limiter = SlidingWindowLimiter(1, 60, clock)
    for index in range(6):
        limiter.hit(f"old-{index}")
    clock.now += 61
    limiter.hit("new")
    assert set(limiter._hits) == {"new"}
