"""
Export Harvest Tracker

Tracks TA export bundle requests in rolling time windows and produces
`export` signals for DETECT-ABU-002 (rapid export after PASS) and
DETECT-ABU-005 (lateral multi-arch export burst).

Signals produced:
  export.harvest_rapid_sequence  — ≥5 exports within 30s of PASS in one session
  export.harvest_count           — count of rapid-export events this session
  export.harvest_session_archs   — arch names involved in rapid exports
  export.lateral_harvest_burst   — ≥3 distinct archs exported within 5 min
  export.lateral_harvest_archs   — arch names in lateral burst
  export.lateral_harvest_count   — number of distinct archs in burst window
"""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Deque, Dict, List, Optional

# ABU-002: rapid export within this many seconds of a PASS gate result
_HARVEST_DELTA_S            = 30
_HARVEST_SESSION_THRESHOLD  = 5   # ≥N rapid-export events = harvest

# ABU-005: lateral harvest burst window and arch threshold
_LATERAL_WINDOW_S   = 300   # 5-minute rolling window
_LATERAL_THRESHOLD  = 3     # ≥N distinct archs exported within window


@dataclass
class ExportSignals:
    harvest_rapid_sequence:  bool  = False
    harvest_count:           int   = 0
    harvest_session_archs:   List[str] = field(default_factory=list)

    lateral_harvest_burst:   bool  = False
    lateral_harvest_archs:   List[str] = field(default_factory=list)
    lateral_harvest_count:   int   = 0

    severity: str  = "LOW"
    flagged:  bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class ExportHarvestTracker:
    """Thread-safe tracker for export bundle requests.

    Call `record_export()` from the export endpoint handler.
    Call `record_pass_gate()` when a pipeline gate result is PASS.
    Call `get_signals()` to get the current export signals dict.
    """

    def __init__(self) -> None:
        self._lock          = threading.Lock()
        self._exports:      Deque[dict] = deque()   # {ts, arch}
        self._pass_events:  Deque[dict] = deque()   # {ts, arch}
        self._rapid_count:  int  = 0
        self._rapid_archs:  List[str] = []

    def record_pass_gate(self, arch_name: str) -> None:
        now = time.time()
        with self._lock:
            self._pass_events.append({"ts": now, "arch": arch_name})
            self._prune(now)

    def record_export(self, arch_name: str) -> None:
        now = time.time()
        with self._lock:
            self._exports.append({"ts": now, "arch": arch_name})
            self._check_rapid(now, arch_name)
            self._prune(now)

    def get_signals(self) -> dict:
        now = time.time()
        with self._lock:
            self._prune(now)
            return {"export": self._compute(now).to_dict()}

    # ── private ──────────────────────────────────────────────────────────────

    def _prune(self, now: float) -> None:
        cutoff = now - max(_LATERAL_WINDOW_S, _HARVEST_DELTA_S * 10)
        while self._exports and self._exports[0]["ts"] < cutoff:
            self._exports.popleft()
        while self._pass_events and self._pass_events[0]["ts"] < cutoff:
            self._pass_events.popleft()

    def _check_rapid(self, now: float, arch_name: str) -> None:
        for ev in self._pass_events:
            if ev["arch"] == arch_name and (now - ev["ts"]) <= _HARVEST_DELTA_S:
                self._rapid_count += 1
                if arch_name not in self._rapid_archs:
                    self._rapid_archs.append(arch_name)
                break

    def _compute(self, now: float) -> ExportSignals:
        sig = ExportSignals()

        sig.harvest_count        = self._rapid_count
        sig.harvest_session_archs = list(self._rapid_archs)
        sig.harvest_rapid_sequence = self._rapid_count >= _HARVEST_SESSION_THRESHOLD

        lateral_cutoff = now - _LATERAL_WINDOW_S
        recent_exports = [e for e in self._exports if e["ts"] >= lateral_cutoff]
        lateral_archs  = list(dict.fromkeys(e["arch"] for e in recent_exports if e["arch"]))
        sig.lateral_harvest_archs = lateral_archs
        sig.lateral_harvest_count = len(lateral_archs)
        sig.lateral_harvest_burst = len(lateral_archs) >= _LATERAL_THRESHOLD

        if sig.harvest_rapid_sequence or sig.lateral_harvest_burst:
            sig.severity = "High"
        sig.flagged = sig.harvest_rapid_sequence or sig.lateral_harvest_burst

        return sig


# Module-level singleton
_tracker = ExportHarvestTracker()


def get_export_tracker() -> ExportHarvestTracker:
    return _tracker
