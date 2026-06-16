"""Adaptive concurrency throttle for polite parallel API access.

A single pause, shared by every worker thread, that grows multiplicatively when
the API rate-limits and decays additively on success. Under heavy 429s the pool
slows to a safe trickle instead of failing; when the API is happy the pause
returns to zero and throughput recovers. The sleep function is injectable so the
backoff logic is tested without real waiting.
"""

import threading
import time
from collections.abc import Callable


class AdaptiveThrottle:
    def __init__(
        self,
        sleep: Callable[[float], None] = time.sleep,
        step: float = 0.5,
        ceiling: float = 30.0,
    ):
        self._sleep = sleep
        self._step = step
        self._ceiling = ceiling
        self._pause = 0.0
        self._lock = threading.Lock()

    @property
    def pause(self) -> float:
        with self._lock:
            return self._pause

    def wait(self) -> None:
        """Block for the current shared pause (no-op while it is zero)."""
        pause = self.pause
        if pause > 0:
            self._sleep(pause)

    def penalize(self) -> None:
        """Rate limit observed: grow the pause (multiplicative increase)."""
        with self._lock:
            self._pause = min(self._ceiling, self._pause * 2 + self._step)

    def relax(self) -> None:
        """Success: decay the pause back toward zero (gradual decrease)."""
        with self._lock:
            self._pause = max(0.0, self._pause - self._step / 4)
