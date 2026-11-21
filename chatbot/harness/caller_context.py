"""Caller attribution for investigation traces (Entry 264).

TA authenticates with one shared API key, so the key cannot say *who* made a
request. This module derives a caller label from request metadata so a run
can be attributed in Langfuse/SIEM.

The label is SELF-ASSERTED when the caller sends a ``TM-CALLER`` header: it
is evidence for an investigator, never an authorisation input (Principle 5).
Pure and deterministic: no I/O, no clock, no LLM.
"""
from __future__ import annotations

import hashlib
import re
from typing import Any, Mapping, Optional

CALLER_HEADER = "TM-CALLER"
_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_MAX_LEN = 64
SOURCES = frozenset({"rest", "mcp", "job", "taclaw", "cli", "unknown"})


def _clean(label: str) -> str:
    return _SAFE.sub("_", label.strip())[:_MAX_LEN]


def build_caller_context(
    headers: Optional[Mapping[str, str]] = None,
    client_host: Optional[str] = None,
    source: str = "rest",
) -> dict[str, Any]:
    """Return ``{caller_id, caller_asserted, source}`` for a request.

    ``caller_asserted`` is True only when the caller supplied a label. With no
    label the id is an ``anon-`` hash of the client host, so repeat callers
    still correlate without storing a raw address.
    """
    src = source if source in SOURCES else "unknown"
    label = ""
    for k, v in (headers or {}).items():
        if k.lower() == CALLER_HEADER.lower():
            label = _clean(v or "")
            break
    if label:
        return {"caller_id": label, "caller_asserted": True, "source": src}
    digest = hashlib.sha256((client_host or "unknown").encode()).hexdigest()[:8]
    return {"caller_id": f"anon-{digest}", "caller_asserted": False, "source": src}
