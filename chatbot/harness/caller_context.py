"""Caller attribution for investigation traces (Entry 264).

TA authenticates with one shared API key, so the key cannot say *who* made a
request. This module derives a caller label from request metadata so a run
can be attributed in Langfuse/SIEM.

The label is SELF-ASSERTED when the caller sends a ``TM-CALLER`` header: it
is evidence for an investigator, never an authorisation input (Principle 5).
No I/O and no LLM; the only clock read is the default session date bucket.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import re
from typing import Any, Mapping, Optional

CALLER_HEADER = "TM-CALLER"
SESSION_HEADER = "TM-SESSION"
_SAFE = re.compile(r"[^A-Za-z0-9._-]")
_MAX_LEN = 64
SOURCES = frozenset({"rest", "mcp", "job", "taclaw", "cli", "unknown"})


def _clean(label: str) -> str:
    return _SAFE.sub("_", label.strip())[:_MAX_LEN]


_PROCESS_SESSION: Optional[str] = None


def process_session() -> str:
    """One session id per client process (``TA_SESSION`` overrides). A client sends
    it as ``TM-SESSION`` so its tool calls and the REST runs they launch group in
    Langfuse. Self-asserted, like the caller label."""
    global _PROCESS_SESSION
    import os
    import uuid
    env = _clean(os.environ.get("TA_SESSION", ""))
    if env:
        return env
    if _PROCESS_SESSION is None:
        _PROCESS_SESSION = f"sess-{uuid.uuid4().hex[:12]}"
    return _PROCESS_SESSION


def _header(headers: Optional[Mapping[str, str]], name: str) -> str:
    for k, v in (headers or {}).items():
        if k.lower() == name.lower():
            return _clean(v or "")
    return ""


def build_caller_context(
    headers: Optional[Mapping[str, str]] = None,
    client_host: Optional[str] = None,
    source: str = "rest",
    today: Optional[str] = None,
) -> dict[str, Any]:
    """Return ``{caller_id, caller_asserted, source, session_id, session_asserted}``.

    ``session_id`` groups related traces in Langfuse. It is the ``TM-SESSION``
    header when sent (self-asserted), else ``<caller_id>:<UTC date>`` so one
    caller's runs on one day still correlate. ``today`` (YYYY-MM-DD) is
    injectable for tests; the default reads the clock, the only impure input.

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
        cid, asserted = label, True
    else:
        digest = hashlib.sha256((client_host or "unknown").encode()).hexdigest()[:8]
        cid, asserted = f"anon-{digest}", False
    sess = _header(headers, SESSION_HEADER)
    if not sess:
        day = today or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d")
        sess = f"{cid}:{day}"[:_MAX_LEN]
    return {"caller_id": cid, "caller_asserted": asserted, "source": src,
            "session_id": sess, "session_asserted": bool(_header(headers, SESSION_HEADER))}
