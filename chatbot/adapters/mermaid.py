"""
Mermaid adapter — wraps existing MermaidParser to produce ArchitectureGraph.

Handles .mmd files so TAclaw can crawl repos that already contain TA diagrams.
Registered first (before generic adapters) so .mmd is always claimed by this adapter.
"""

from __future__ import annotations

from pathlib import Path
from typing import Tuple, List

from chatbot.adapters.base import ArchEdge, ArchitectureGraph, ArchNode, BaseAdapter, NodeType, _safe_id
from chatbot.adapters.registry import register


def _shape_to_node_type(shape: str) -> NodeType:
    return {
        "cylinder": "database",
        "stadium":  "external",
        "diamond":  "network",
        "asymmetric": "queue",
        "rect":     "service",
        "default":  "service",
    }.get(shape, "service")


class MermaidAdapter(BaseAdapter):
    source_formats = ["mmd"]

    def can_handle(self, filename: str, content_peek: bytes) -> bool:
        return Path(filename).suffix.lower() == ".mmd"

    def extract(self, content: str | bytes, filename: str = "") -> ArchitectureGraph:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        try:
            from chatbot.modules.ground_truth_generator import parse_mermaid_file
            import tempfile, os
            with tempfile.NamedTemporaryFile(mode="w", suffix=".mmd", delete=False, encoding="utf-8") as tmp:
                tmp.write(content)
                tmp_path = tmp.name
            try:
                parsed = parse_mermaid_file(tmp_path)
            finally:
                os.unlink(tmp_path)

            nodes = [
                ArchNode(
                    id=_safe_id(nid),
                    label=ndata.get("label", nid),
                    node_type=_shape_to_node_type(ndata.get("shape", "rect")),
                )
                for nid, ndata in parsed.get("nodes", {}).items()
            ]
            edges = [
                ArchEdge(
                    source=_safe_id(e["source"]),
                    target=_safe_id(e["target"]),
                    label=e.get("label") or None,
                )
                for e in parsed.get("edges", [])
            ]
        except Exception:
            # Minimal fallback: single node
            nodes = [ArchNode(id="arch", label=Path(filename).stem or "architecture", node_type="service")]
            edges = []

        title = Path(filename).stem or "mermaid"
        return ArchitectureGraph(
            title=title,
            nodes=nodes,
            edges=edges,
            source_format="mmd",
            adapter_metadata={
                "filename": filename,
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        )


# Self-register first — .mmd check is fast (extension only) so it runs before content-based adapters
register(MermaidAdapter())
