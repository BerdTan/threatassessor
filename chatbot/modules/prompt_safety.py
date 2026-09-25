"""
prompt_safety — sanitise external content before LLM prompt interpolation.

Two helpers:
  sanitise_arch_name(name)       — filesystem-derived arch identifier; strip to safe chars
  sanitise_content(text, max_len) — larger external content (MMD, crawled text); remove injection patterns

Both are conservative: they only strip known-bad patterns and cap length.
They do NOT parse or validate content semantics.
"""
from __future__ import annotations

import re

# Common prompt injection openers — patterns that attempt to override system instructions
# from within user-supplied content (MITRE T1562 / DETECT-QC-009 vector).
_INJECTION_RE = re.compile(
    r'(?:'
    r'ignore\s+(?:previous|prior|all|your\s+previous)\s+instructions?'
    r'|forget\s+(?:your\s+)?(?:previous|prior|all)\s+instructions?'
    r'|you\s+are\s+now\s+(?:a|an)\s+'
    r'|act\s+as\s+(?:a|an)\s+(?:new|different)\s+'
    r'|override\s+(?:your\s+)?(?:previous|prior)\s+instructions?'
    r'|disregard\s+(?:your\s+)?(?:previous|prior)\s+instructions?'
    r'|new\s+instructions?:\s*'
    r'|system\s+prompt:\s*'
    r'|<\s*/?(?:system|instruction|prompt|role)\s*>'
    r'|you\s+must\s+now\s+(?:instead|only)'
    r'|your\s+(?:new\s+)?(?:role|task|goal|job)\s+is\s+now'
    r')',
    re.IGNORECASE,
)

# arch_name is always a filesystem-derived identifier (e.g. "01_minimal_vulnerable").
# Permit alphanumerics, underscores, hyphens, dots; collapse anything else to underscore.
_ARCH_NAME_UNSAFE_RE = re.compile(r'[^\w\-.]')

_ARCH_NAME_MAX = 200
_CONTENT_MAX_DEFAULT = 60_000


def sanitise_arch_name(name: str) -> str:
    """Strip arch_name to safe filesystem-identifier characters and cap length."""
    if not isinstance(name, str):
        name = str(name)
    cleaned = _ARCH_NAME_UNSAFE_RE.sub('_', name)
    return cleaned[:_ARCH_NAME_MAX]


def sanitise_content(text: str, max_len: int = _CONTENT_MAX_DEFAULT) -> str:
    """Remove known prompt-injection patterns from external content and cap length.

    Used for architecture diagram text, crawled content, and any other
    externally-ingested string that flows into a prompt f-string.
    """
    if not isinstance(text, str):
        text = str(text)
    cleaned = _INJECTION_RE.sub('[FILTERED]', text)
    return cleaned[:max_len]
