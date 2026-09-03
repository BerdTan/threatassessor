"""
Adapter registry — auto-detection of artifact format.

Adapters self-register at import time by calling register().
detect_adapter() returns the first adapter that claims can_handle().
"""

from __future__ import annotations

from typing import List

from chatbot.adapters.base import BaseAdapter

_ADAPTERS: List[BaseAdapter] = []


def register(adapter: BaseAdapter) -> None:
    """Register an adapter instance. Call at module level from each adapter module."""
    _ADAPTERS.append(adapter)


def detect_adapter(filename: str, content: bytes) -> BaseAdapter:
    """Return the first registered adapter that claims can_handle(filename, content[:512]).

    Raises ValueError if no adapter matches.
    """
    peek = content[:512]
    for adapter in _ADAPTERS:
        if adapter.can_handle(filename, peek):
            return adapter
    raise ValueError(
        f"No adapter found for '{filename}'. "
        f"Supported formats: Terraform (.tf, plan.json), CloudFormation (.yaml/.yml/.json with AWSTemplateFormatVersion), "
        f"OpenAPI/AsyncAPI (.yaml/.yml/.json with openapi:/asyncapi: key), prose (.md, .txt)."
    )


def list_adapters() -> List[str]:
    """Return names of all registered adapters."""
    return [type(a).__name__ for a in _ADAPTERS]
