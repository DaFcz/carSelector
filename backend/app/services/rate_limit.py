"""In-process sliding-window rate limiting, for limits that don't need to
survive a restart or be shared between worker processes (the same
single-process assumption `app/services/conversation.py`'s in-memory
conversations already make).

Login-code limits don't use this: they count rows in `login_codes`
instead (see `app/services/auth.py`), so they hold across restarts.
"""

import threading
import time
from collections import deque
from collections.abc import Callable


class SlidingWindowLimiter:
    """Allows at most `limit` hits per key within any `window_seconds`.

    Thread-safe: the UI calls the service layer from `run.io_bound` worker
    threads, and FastAPI runs sync endpoints in a thread pool.
    """

    # Above this many tracked keys, a hit also sweeps keys whose hits have
    # all aged out - bounds memory against many distinct keys (e.g. IPs).
    _SWEEP_THRESHOLD = 10_000

    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        """Args:
        limit: Hits allowed per key per window. 0 or less disables the
            limit (every hit is allowed).
        window_seconds: Length of the sliding window.
        clock: Monotonic time source (a parameter so tests control it).
        """
        self._limit = limit
        self._window = window_seconds
        self._clock = clock
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> bool:
        """Records a hit for `key` if it is within the limit.

        Args:
            key: What the limit applies to, e.g. a client IP.

        Returns:
            True if the hit is allowed (and was recorded), False if `key`
            already used up its limit in the current window.
        """
        if self._limit <= 0:
            return True
        now = self._clock()
        cutoff = now - self._window
        with self._lock:
            if len(self._hits) > self._SWEEP_THRESHOLD:
                self._sweep(cutoff)
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self._limit:
                return False
            hits.append(now)
            return True

    def _sweep(self, cutoff: float) -> None:
        """Drops keys with no hit newer than `cutoff`. Caller holds the lock."""
        for key in [key for key, hits in self._hits.items() if not hits or hits[-1] <= cutoff]:
            del self._hits[key]
