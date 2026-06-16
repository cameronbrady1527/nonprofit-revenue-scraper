"""Adaptive throttle: multiplicative back-off, gradual recovery (offline)."""

from nonprofit_benchmark.throttle import AdaptiveThrottle


def test_starts_at_zero_and_wait_is_a_noop():
    slept = []
    throttle = AdaptiveThrottle(sleep=slept.append)
    assert throttle.pause == 0.0
    throttle.wait()
    assert slept == []  # no waiting while healthy


def test_penalize_grows_multiplicatively():
    throttle = AdaptiveThrottle(sleep=lambda s: None, step=0.5)
    throttle.penalize()
    assert throttle.pause == 0.5  # 0 * 2 + 0.5
    throttle.penalize()
    assert throttle.pause == 1.5  # 0.5 * 2 + 0.5


def test_pause_is_capped_at_ceiling():
    throttle = AdaptiveThrottle(sleep=lambda s: None, step=10, ceiling=5)
    for _ in range(5):
        throttle.penalize()
    assert throttle.pause == 5


def test_relax_decays_gradually_and_never_negative():
    throttle = AdaptiveThrottle(sleep=lambda s: None, step=0.5)
    throttle.penalize()
    throttle.penalize()
    throttle.relax()
    assert throttle.pause == 1.5 - 0.125  # step / 4
    for _ in range(100):
        throttle.relax()
    assert throttle.pause == 0.0


def test_wait_sleeps_for_the_current_pause():
    slept = []
    throttle = AdaptiveThrottle(sleep=slept.append, step=0.5)
    throttle.penalize()
    throttle.wait()
    assert slept == [0.5]
