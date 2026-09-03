"""
TA adapter foundation — canonical intermediate types and base adapter contract.

All input adapters (Terraform, CloudFormation, OpenAPI, prose, …) produce an
ArchitectureGraph, which can be serialised to Mermaid text for the existing TA
pipeline or to an architecture_data dict for ThreatAnalysisService.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from typing import Any, ClassVar, Dict, List, Literal, Optional

from pydantic import BaseModel, Field


# ── node / edge types ─────────────────────────────────────────────────────────

NodeType = Literal[
    "service", "database", "network", "external", "queue", "storage", "unknown"
]

_MMD_SHAPE: Dict[str, tuple[str, str]] = {
    "service":  ("[", "]"),
    "database": ("[(", ")]"),
    "storage":  ("[(", ")]"),
    "network":  ("{", "}"),
    "external": ("([", "])"),
    "queue":    (">", "]"),
    "unknown":  ("[", "]"),
}

_SHAPE_TO_MMD: Dict[str, str] = {
    "rect":     "service",
    "cylinder": "database",
    "diamond":  "network",
    "stadium":  "external",
    "default":  "unknown",
}


def _safe_id(raw: str) -> str:
    """Sanitise a node id for use in Mermaid (no spaces, no special chars)."""
    return re.sub(r"[^A-Za-z0-9_]", "_", raw)


class ArchNode(BaseModel):
    id: str
    label: str
    node_type: NodeType = "unknown"
    trust_zone: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ArchEdge(BaseModel):
    source: str
    target: str
    label: Optional[str] = None
    protocol: Optional[str] = None


# ── graph ─────────────────────────────────────────────────────────────────────

class ArchitectureGraph(BaseModel):
    title: str = "untitled"
    nodes: List[ArchNode] = Field(default_factory=list)
    edges: List[ArchEdge] = Field(default_factory=list)
    source_format: str = "unknown"      # "terraform" | "cloudformation" | "openapi" | "prose" | "mmd"
    adapter_metadata: Dict[str, Any] = Field(default_factory=dict)

    def to_mmd(self) -> str:
        """Emit a valid Mermaid flowchart LR diagram from this graph."""
        lines = [f"flowchart LR"]
        for node in self.nodes:
            nid = _safe_id(node.id)
            label = node.label.replace('"', "'")
            open_, close = _MMD_SHAPE.get(node.node_type, ("[", "]"))
            lines.append(f'    {nid}{open_}"{label}"{close}')
        for edge in self.edges:
            src = _safe_id(edge.source)
            tgt = _safe_id(edge.target)
            if edge.label:
                arrow = f'-->|"{edge.label}"|'
            else:
                arrow = "-->"
            lines.append(f"    {src} {arrow} {tgt}")
        return "\n".join(lines)

    def to_architecture_data(self) -> Dict:
        """
        Return the dict shape that ThreatAnalysisService.architecture_data expects:
        {nodes: {id: {label, shape}}, edges: [{source, target, label}], subgraphs: {}}
        """
        nodes = {
            _safe_id(n.id): {
                "label": n.label,
                "shape": _node_type_to_shape(n.node_type),
            }
            for n in self.nodes
        }
        edges = [
            {
                "source": _safe_id(e.source),
                "target": _safe_id(e.target),
                "label":  e.label or "",
            }
            for e in self.edges
        ]
        return {"nodes": nodes, "edges": edges, "subgraphs": {}}


def _node_type_to_shape(node_type: NodeType) -> str:
    return {
        "service":  "rect",
        "database": "cylinder",
        "storage":  "cylinder",
        "network":  "diamond",
        "external": "stadium",
        "queue":    "asymmetric",
        "unknown":  "rect",
    }.get(node_type, "rect")


# ── base adapter ──────────────────────────────────────────────────────────────

class BaseAdapter(ABC):
    source_formats: ClassVar[List[str]] = []

    @abstractmethod
    def can_handle(self, filename: str, content_peek: bytes) -> bool:
        """Return True if this adapter can process the given file."""

    @abstractmethod
    def extract(self, content: str | bytes, filename: str = "") -> ArchitectureGraph:
        """Parse content and return an ArchitectureGraph."""
