"""
Shared slowapi limiter instance.

Import `limiter` here rather than instantiating it in each route module —
slowapi's state tracking is per-limiter-instance, so a single shared object
ensures limits accumulate correctly across all requests.
"""

import threading

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


class _RateLimitCounter:
    """Thread-safe counter for 429 responses — feeds rest_api.rate_limited_count signal."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._count = 0

    def increment(self) -> None:
        with self._lock:
            self._count += 1

    def get(self) -> int:
        with self._lock:
            return self._count


rate_limit_counter = _RateLimitCounter()
