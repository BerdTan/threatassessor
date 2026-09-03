"""
Prose adapter — LLM-assisted extraction of architecture from text documents.

Handles: .md, .txt, .pdf (optional PyMuPDF), .docx (optional python-docx)

Uses agentic/llm_client.LLMClient (existing in codebase — no new LLM path).
Falls back gracefully if LLM unavailable: returns a single-node graph.

Optional extras for binary formats:
  pip install PyMuPDF       # for .pdf
  pip install python-docx   # for .docx
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from chatbot.adapters.base import ArchEdge, ArchitectureGraph, ArchNode, BaseAdapter, NodeType
from chatbot.adapters.registry import register

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = {"md", "txt", "pdf", "docx", "rst"}

_EXTRACTION_PROMPT = """\
You are a software architecture analyst. Extract the architecture components and their relationships from the text below.

Return ONLY valid JSON with this exact structure:
{
  "title": "<brief architecture name>",
  "nodes": [
    {"id": "<snake_case_id>", "label": "<Human Readable Label>", "type": "<service|database|network|external|queue|storage|unknown>"}
  ],
  "edges": [
    {"source": "<id>", "target": "<id>", "label": "<optional relationship description>"}
  ]
}

Rules:
- Identify distinct components: services, databases, queues, APIs, external systems
- Each node id must be unique snake_case, no spaces
- Only include edges where a clear relationship is stated or strongly implied
- If no clear architecture is described, return a single node with type "service" named after the document title
- Return ONLY the JSON object, no explanation

TEXT:
"""


def _extract_text_from_pdf(content: bytes) -> str:
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(stream=content, filetype="pdf")
        return "\n".join(page.get_text() for page in doc)
    except ImportError:
        raise ImportError(
            "PDF extraction requires PyMuPDF: pip install PyMuPDF"
        )


def _extract_text_from_docx(content: bytes) -> str:
    try:
        import docx
        import io
        doc = docx.Document(io.BytesIO(content))
        return "\n".join(p.text for p in doc.paragraphs)
    except ImportError:
        raise ImportError(
            "DOCX extraction requires python-docx: pip install python-docx"
        )


def _extract_text(content: str | bytes, filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    if ext == "pdf":
        if isinstance(content, str):
            content = content.encode("utf-8")
        return _extract_text_from_pdf(content)
    if ext == "docx":
        if isinstance(content, str):
            content = content.encode("utf-8")
        return _extract_text_from_docx(content)
    if isinstance(content, bytes):
        return content.decode("utf-8", errors="replace")
    return content


def _call_llm(text: str) -> Optional[Dict]:
    """Call LLMClient for structured JSON extraction. Returns None on failure."""
    try:
        from agentic.llm_client import LLMClient
        client = LLMClient()
        prompt = _EXTRACTION_PROMPT + text[:8000]  # cap at 8k chars
        response = client.complete(prompt, max_tokens=2000, temperature=0)
        raw = response.strip() if isinstance(response, str) else ""
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)
    except Exception as exc:
        logger.warning("ProseAdapter LLM call failed: %s", exc)
        return None


def _fallback_graph(text: str, title: str) -> Tuple[List[ArchNode], List[ArchEdge]]:
    """Keyword-based fallback: extract noun phrases that look like component names."""
    keywords = {
        "service": "service", "api": "service", "gateway": "network",
        "database": "database", "db": "database", "cache": "database",
        "queue": "queue", "broker": "queue", "stream": "queue",
        "storage": "storage", "bucket": "storage", "blob": "storage",
        "load balancer": "network", "proxy": "network", "cdn": "network",
        "client": "external", "user": "external", "browser": "external",
    }
    nodes: List[ArchNode] = []
    seen: set = set()
    text_lower = text.lower()
    for keyword, node_type in keywords.items():
        if keyword in text_lower:
            nid = keyword.replace(" ", "_")
            if nid not in seen:
                seen.add(nid)
                nodes.append(ArchNode(id=nid, label=keyword.title(), node_type=node_type))  # type: ignore[arg-type]
    if not nodes:
        nodes = [ArchNode(id="system", label=title, node_type="service")]
    return nodes, []


def _parse_llm_response(data: Dict) -> Tuple[List[ArchNode], List[ArchEdge]]:
    nodes: List[ArchNode] = []
    edges: List[ArchEdge] = []
    valid_types = {"service", "database", "network", "external", "queue", "storage", "unknown"}

    for n in data.get("nodes", []):
        ntype = n.get("type", "unknown")
        if ntype not in valid_types:
            ntype = "unknown"
        nodes.append(ArchNode(
            id=str(n.get("id", f"node_{len(nodes)}")),
            label=str(n.get("label", n.get("id", "Component"))),
            node_type=ntype,  # type: ignore[arg-type]
        ))

    node_ids = {n.id for n in nodes}
    for e in data.get("edges", []):
        src = str(e.get("source", ""))
        tgt = str(e.get("target", ""))
        if src in node_ids and tgt in node_ids:
            edges.append(ArchEdge(
                source=src,
                target=tgt,
                label=e.get("label") or None,
            ))

    return nodes, edges


# ── adapter ───────────────────────────────────────────────────────────────────

class ProseAdapter(BaseAdapter):
    source_formats = list(_SUPPORTED_EXTENSIONS)

    def can_handle(self, filename: str, content_peek: bytes) -> bool:
        ext = Path(filename).suffix.lstrip(".").lower()
        return ext in _SUPPORTED_EXTENSIONS

    def extract(self, content: str | bytes, filename: str = "") -> ArchitectureGraph:
        title = Path(filename).stem or "architecture"
        try:
            text = _extract_text(content, filename)
        except ImportError as e:
            logger.warning("ProseAdapter: %s", e)
            text = content.decode("utf-8", errors="replace") if isinstance(content, bytes) else str(content)

        llm_data = _call_llm(text)
        if llm_data and isinstance(llm_data, dict):
            nodes, edges = _parse_llm_response(llm_data)
            title = str(llm_data.get("title", title))[:80]
            method = "llm"
        else:
            nodes, edges = _fallback_graph(text, title)
            method = "keyword_fallback"

        return ArchitectureGraph(
            title=title,
            nodes=nodes,
            edges=edges,
            source_format="prose",
            adapter_metadata={
                "filename": filename,
                "extraction_method": method,
                "text_length": len(text),
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        )


# Self-register (last — prose is the catch-all for text files)
register(ProseAdapter())
