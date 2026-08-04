"""
MCP Access Logger

Tracks tool call patterns in a rolling time window and produces an `mcp_access`
signals dict that can be merged into governance_signals.json for DETECT rule evaluation.

Three signals are produced:
  mcp_access.recon_sequence      — bulk list+governance calls (discovery pattern)
  mcp_access.job_flood           — expert review submissions without polling (resource abuse)
  mcp_access.auth_failures       — repeated 401 responses (credential probing)

These feed DETECT-020, DETECT-021, DETECT-022 respectively.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from dataclasses import dataclass, field, asdict
from typing import Deque, Dict, List, Optional

# Windows for pattern detection
_RECON_WINDOW_S     = 60    # list+bulk-gov calls within this window = recon
_FLOOD_WINDOW_S     = 120   # review submissions within this window = flood
_AUTH_WINDOW_S      = 300   # auth failures within this window = probing

_RECON_GOV_THRESHOLD  = 3   # ≥N unique archs queried via get_governance_signals
_FLOOD_JOB_THRESHOLD  = 3   # ≥N expert review submissions
_FLOOD_POLL_RATIO     = 0.5 # poll_count / submit_count < this = flood (not polling back)
_AUTH_FAIL_THRESHOLD  = 5   # ≥N auth failures


@dataclass
class MCPAccessSignals:
    # Recon pattern: list_architectures followed by bulk governance signal pulls
    recon_sequence:          bool = False
    recon_list_calls:        int  = 0
    recon_gov_archs:         int  = 0   # unique archs queried for governance signals
    recon_window_seconds:    int  = _RECON_WINDOW_S

    # Job flood: expert review submissions without corresponding polls
    job_flood:               bool  = False
    job_flood_submissions:   int   = 0
    job_flood_polls:         int   = 0
    job_flood_ratio:         float = 0.0  # polls / submissions (low = flood)
    job_flood_window_seconds: int  = _FLOOD_WINDOW_S

    # Auth probing: repeated 401 responses
    auth_failures:           bool = False
    auth_failure_count:      int  = 0
    auth_failure_window_s:   int  = _AUTH_WINDOW_S

    # Meta
    total_tool_calls:   int   = 0
    unique_tools_called: int  = 0
    session_duration_s:  float = 0.0
    first_call_ts:       float = 0.0
    last_call_ts:        float = 0.0
    severity:            str  = "LOW"
    flagged:             bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class MCPAccessLogger:
    """Thread-safe rolling-window tracker for MCP tool call patterns.

    Instantiate once per server process. Call `record_tool_call()` from each
    tool handler. Call `get_signals()` to get the current mcp_access dict for
    DETECT rule evaluation.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._calls:         Deque[dict] = deque()   # {ts, tool, arch, success}
        self._auth_failures: Deque[float] = deque()  # timestamps of 401s
        self._session_start: Optional[float] = None

    def record_tool_call(
        self,
        tool_name: str,
        arch_name: str = "",
        success: bool = True,
        auth_failed: bool = False,
    ) -> None:
        now = time.time()
        with self._lock:
            if self._session_start is None:
                self._session_start = now
            self._calls.append({
                "ts":      now,
                "tool":    tool_name,
                "arch":    arch_name,
                "success": success,
            })
            if auth_failed:
                self._auth_failures.append(now)
            self._prune(now)

    def get_signals(self) -> dict:
        now = time.time()
        with self._lock:
            self._prune(now)
            return self._compute(now)

    # ── private ──────────────────────────────────────────────────────────────

    def _prune(self, now: float) -> None:
        max_window = max(_RECON_WINDOW_S, _FLOOD_WINDOW_S, _AUTH_WINDOW_S)
        cutoff = now - max_window
        while self._calls and self._calls[0]["ts"] < cutoff:
            self._calls.popleft()
        auth_cutoff = now - _AUTH_WINDOW_S
        while self._auth_failures and self._auth_failures[0] < auth_cutoff:
            self._auth_failures.popleft()

    def _compute(self, now: float) -> dict:
        sig = MCPAccessSignals()

        calls = list(self._calls)
        if not calls:
            return {"mcp_access": sig.to_dict()}

        sig.first_call_ts   = calls[0]["ts"]
        sig.last_call_ts    = calls[-1]["ts"]
        sig.total_tool_calls = len(calls)
        sig.unique_tools_called = len({c["tool"] for c in calls})
        sig.session_duration_s = (
            now - self._session_start if self._session_start else 0.0
        )

        # ── Recon pattern ─────────────────────────────────────────────────
        recon_cutoff = now - _RECON_WINDOW_S
        recon_calls = [c for c in calls if c["ts"] >= recon_cutoff]
        list_calls  = [c for c in recon_calls if c["tool"] == "list_architectures"]
        gov_calls   = [c for c in recon_calls if c["tool"] == "get_governance_signals"]
        gov_archs   = {c["arch"] for c in gov_calls if c["arch"]}

        sig.recon_list_calls = len(list_calls)
        sig.recon_gov_archs  = len(gov_archs)
        sig.recon_sequence   = (
            len(list_calls) >= 1 and len(gov_archs) >= _RECON_GOV_THRESHOLD
        )

        # ── Job flood ─────────────────────────────────────────────────────
        flood_cutoff  = now - _FLOOD_WINDOW_S
        flood_calls   = [c for c in calls if c["ts"] >= flood_cutoff]
        submissions   = [c for c in flood_calls if c["tool"] == "run_expert_review"]
        polls         = [c for c in flood_calls if c["tool"] == "get_job_status"]
        sub_count     = len(submissions)
        poll_count    = len(polls)
        poll_ratio    = (poll_count / sub_count) if sub_count > 0 else 1.0

        sig.job_flood_submissions  = sub_count
        sig.job_flood_polls        = poll_count
        sig.job_flood_ratio        = round(poll_ratio, 3)
        sig.job_flood              = (
            sub_count >= _FLOOD_JOB_THRESHOLD
            and poll_ratio < _FLOOD_POLL_RATIO
        )

        # ── Auth failures ─────────────────────────────────────────────────
        auth_count           = len(self._auth_failures)
        sig.auth_failure_count = auth_count
        sig.auth_failures      = auth_count >= _AUTH_FAIL_THRESHOLD

        # ── Severity roll-up ──────────────────────────────────────────────
        flagged_signals = [sig.recon_sequence, sig.job_flood, sig.auth_failures]
        n_flagged       = sum(flagged_signals)
        if sig.auth_failures:
            sig.severity = "High"
        elif sig.job_flood:
            sig.severity = "High"
        elif sig.recon_sequence:
            sig.severity = "Medium"
        else:
            sig.severity = "LOW"
        sig.flagged = n_flagged > 0

        return {"mcp_access": sig.to_dict()}


# Module-level singleton — shared across the server process
_logger = MCPAccessLogger()


def get_access_logger() -> MCPAccessLogger:
    return _logger
