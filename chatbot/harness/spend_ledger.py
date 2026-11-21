"""Per-caller spend ledger (Entry 264, step 3).

A sliding-window count of spend attempts and tokens per caller. The spend gate
reads it to return ``throttle``. In-process and deterministic: no I/O, no LLM.

Limits are SOFT. ``caller_id`` is self-asserted (``TM-CALLER`` header) or an
``anon-`` hash of the client host, so on a shared API key a caller can rotate
its label and reset its own counter. Real per-caller enforcement needs
per-caller keys (a later step). Until then this is measurement plus a throttle
that stops accidental loops and a single noisy host, not a defence against a
determined abuser (Principle 4: say what is not covered).

Tokens are counted only where the harness reports them (critic generation);
analysis-stage calls do not emit usage events. Request count is the reliable
dimension.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Callable, Deque, Dict, Tuple

_MAX_CALLERS = 5000  # bound memory: oldest-idle callers are dropped past this


class SpendLedger:
    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        # caller -> deque[(ts, requests, tokens)]
        self._events: Dict[str, Deque[Tuple[float, int, int]]] = defaultdict(deque)

    def record(self, caller_id: str, requests: int = 0, tokens: int = 0) -> None:
        if not caller_id or (requests <= 0 and tokens <= 0):
            return
        with self._lock:
            if caller_id not in self._events and len(self._events) >= _MAX_CALLERS:
                oldest = min(self._events, key=lambda c: self._events[c][-1][0])
                del self._events[oldest]
            self._events[caller_id].append((self._clock(), max(requests, 0), max(tokens, 0)))

    def totals(self, caller_id: str, window_s: float) -> Dict[str, int]:
        """Requests and tokens for a caller within the last ``window_s`` seconds."""
        cutoff = self._clock() - window_s
        with self._lock:
            q = self._events.get(caller_id)
            if q is None:
                return {"requests": 0, "tokens": 0}
            while q and q[0][0] < cutoff:  # prune; window only ever moves forward
                q.popleft()
            return {
                "requests": sum(e[1] for e in q),
                "tokens": sum(e[2] for e in q),
            }

    def reset(self) -> None:
        with self._lock:
            self._events.clear()


LEDGER = SpendLedger()
