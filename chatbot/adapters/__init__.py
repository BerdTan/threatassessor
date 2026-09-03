from chatbot.adapters.base import ArchitectureGraph, ArchEdge, ArchNode, BaseAdapter
from chatbot.adapters.registry import detect_adapter, list_adapters, register

# Import adapters to trigger self-registration
import chatbot.adapters.terraform       # noqa: F401
import chatbot.adapters.cloudformation  # noqa: F401
import chatbot.adapters.openapi         # noqa: F401
import chatbot.adapters.prose           # noqa: F401

__all__ = [
    "ArchitectureGraph", "ArchEdge", "ArchNode", "BaseAdapter",
    "detect_adapter", "list_adapters", "register",
]
