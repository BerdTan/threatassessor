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

    Falls back to Jev choice when no adapter matches. Raises ValueError if both fail.
    """
    peek = content[:512]
    for adapter in _ADAPTERS:
        if adapter.can_handle(filename, peek):
            return adapter

    # Jev fallback — try choice when no adapter claims the file
    from chatbot.modules.jev_client import get_jev_client as _get_jev
    _jev = _get_jev()
    if _jev.is_enabled():
        try:
            _sample = content[:800].decode("utf-8", errors="replace")
        except Exception:
            _sample = ""
        if _sample:
            _answers = _jev.ask(
                state={"filename": filename, "content_sample": _sample},
                questions={
                    "adapter": {
                        "type": "choice",
                        "criteria": {
                            "MermaidAdapter":        "Mermaid diagram (.mmd, graph LR/TD/flowchart syntax)",
                            "TerraformAdapter":      "HashiCorp Terraform HCL (.tf files, resource/provider blocks)",
                            "CloudFormationAdapter": "AWS CloudFormation YAML/JSON (AWSTemplateFormatVersion key)",
                            "OpenAPIAdapter":        "OpenAPI or AsyncAPI specification (openapi:/asyncapi: key)",
                            "ProseAdapter":          "Free-form text, markdown, architecture description prose",
                        },
                    }
                },
            )
            _choice = _answers.get("adapter", {}).get("choice")
            _conf = float(_answers.get("adapter", {}).get("confidence", 0.0))
            if _choice and _conf >= 0.80:
                for adapter in _ADAPTERS:
                    if type(adapter).__name__ == _choice:
                        return adapter

    raise ValueError(
        f"No adapter found for '{filename}'. "
        f"Supported formats: Terraform (.tf, plan.json), CloudFormation (.yaml/.yml/.json with AWSTemplateFormatVersion), "
        f"OpenAPI/AsyncAPI (.yaml/.yml/.json with openapi:/asyncapi: key), prose (.md, .txt)."
    )


def list_adapters() -> List[str]:
    """Return names of all registered adapters."""
    return [type(a).__name__ for a in _ADAPTERS]
