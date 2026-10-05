import threading
import time

import pytest

from mlb_baseball.net import RateLimiter


def test_acquire_spaces_calls_across_threads():
    limiter = RateLimiter(100.0)  # 10 ms apart
    stamps = []

    def work():
        limiter.acquire()
        stamps.append(time.monotonic())

    threads = [threading.Thread(target=work) for _ in range(20)]
    start = time.monotonic()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max(stamps) - start >= 0.17  # 20 calls cannot finish faster than 19 intervals


def test_slow_down_halves_the_rate_and_speed_up_recovers_to_the_ceiling():
    limiter = RateLimiter(80.0, min_rate=5.0)
    limiter.slow_down()
    assert limiter.rate == 40.0
    for _ in range(100):
        limiter.speed_up()
    assert limiter.rate == 80.0  # never above the configured ceiling


def test_slow_down_never_goes_below_the_floor():
    limiter = RateLimiter(10.0, min_rate=4.0)
    for _ in range(10):
        limiter.slow_down()
    assert limiter.rate == 4.0


def test_a_non_positive_rate_is_rejected():
    with pytest.raises(ValueError):
        RateLimiter(0)
