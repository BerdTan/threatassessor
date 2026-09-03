"""
OpenAPI / AsyncAPI adapter — converts API specs to ArchitectureGraph.

Handles:
  - OpenAPI 3.x (openapi: "3.x.x" key)
  - Swagger 2.x (swagger: "2.x" key)
  - AsyncAPI 2.x (asyncapi: "2.x.x" key)

Nodes: one per path-prefix group + data schemas + external servers + auth schemes.
Edges: endpoint → schema references, security scheme references.

Uses yaml.safe_load + stdlib json — no new dependencies.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

from chatbot.adapters.base import ArchEdge, ArchitectureGraph, ArchNode, BaseAdapter, NodeType
from chatbot.adapters.registry import register


def _first_segment(path: str) -> str:
    """Extract first path segment: '/users/{id}/orders' → '/users'."""
    parts = [p for p in path.split("/") if p and not p.startswith("{")]
    return f"/{parts[0]}" if parts else "/"


def _label_from_path(segment: str) -> str:
    return segment.strip("/").replace("-", " ").replace("_", " ").title() or "Root"


# ── OpenAPI / Swagger parser ──────────────────────────────────────────────────

def _parse_openapi(data: Dict) -> Tuple[List[ArchNode], List[ArchEdge]]:
    nodes: Dict[str, ArchNode] = {}
    edges: List[ArchEdge] = []
    seen_edges: Set[Tuple[str, str]] = set()

    def _add_edge(src: str, tgt: str, label: Optional[str] = None) -> None:
        if src != tgt and (src, tgt) not in seen_edges:
            seen_edges.add((src, tgt))
            edges.append(ArchEdge(source=src, target=tgt, label=label))

    # External servers → "external" nodes
    for server in data.get("servers", []):
        url = server.get("url", "")
        if url and not url.startswith("/") and "localhost" not in url and "127.0.0.1" not in url:
            node_id = f"server_{len(nodes)}"
            nodes[node_id] = ArchNode(id=node_id, label=url[:60], node_type="external")

    # Security schemes → "service" nodes (auth services)
    sec_schemes = (
        data.get("components", {}).get("securitySchemes", {})
        or data.get("securityDefinitions", {})
    )
    auth_nodes: Dict[str, str] = {}
    for scheme_name, scheme_def in sec_schemes.items():
        node_id = f"auth_{scheme_name}"
        scheme_type = scheme_def.get("type", "auth") if isinstance(scheme_def, dict) else "auth"
        nodes[node_id] = ArchNode(
            id=node_id,
            label=f"{scheme_name} ({scheme_type})",
            node_type="service",
            metadata={"scheme_type": scheme_type},
        )
        auth_nodes[scheme_name] = node_id

    # Path groups → "service" nodes
    path_groups: Dict[str, str] = {}  # prefix → node_id
    for path, path_item in (data.get("paths") or {}).items():
        prefix = _first_segment(path)
        if prefix not in path_groups:
            node_id = f"svc_{prefix.strip('/') or 'root'}"
            label = _label_from_path(prefix) + " Service"
            nodes[node_id] = ArchNode(id=node_id, label=label, node_type="service")
            path_groups[prefix] = node_id

        svc_id = path_groups[prefix]

        # Security on operations → edges to auth nodes
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method not in ("get", "post", "put", "patch", "delete", "head", "options"):
                continue
            if not isinstance(op, dict):
                continue
            for sec_req in op.get("security", []):
                for sec_name in sec_req:
                    if sec_name in auth_nodes:
                        _add_edge(svc_id, auth_nodes[sec_name], "secured_by")

            # Request body schema refs
            body = op.get("requestBody", {})
            _extract_schema_edges(body, svc_id, data, nodes, edges, seen_edges)

            # Response schema refs
            for resp in op.get("responses", {}).values():
                _extract_schema_edges(resp, svc_id, data, nodes, edges, seen_edges)

    # Data schemas from components
    for schema_name, schema_def in (data.get("components", {}).get("schemas", {}) or {}).items():
        if not isinstance(schema_def, dict):
            continue
        kind = schema_def.get("type", "object")
        if kind in ("object", "array") or "properties" in schema_def:
            node_id = f"schema_{schema_name}"
            if node_id not in nodes:
                nodes[node_id] = ArchNode(
                    id=node_id,
                    label=f"{schema_name} (data)",
                    node_type="database",
                )

    return list(nodes.values()), edges


def _extract_schema_edges(
    obj: Any,
    source_id: str,
    spec: Dict,
    nodes: Dict[str, ArchNode],
    edges: List[ArchEdge],
    seen: Set[Tuple[str, str]],
) -> None:
    """Follow $ref pointers to component schemas and create edges."""
    if not isinstance(obj, dict):
        return
    ref = obj.get("$ref", "")
    if ref.startswith("#/components/schemas/"):
        schema_name = ref.split("/")[-1]
        node_id = f"schema_{schema_name}"
        if node_id not in nodes:
            nodes[node_id] = ArchNode(
                id=node_id, label=f"{schema_name} (data)", node_type="database"
            )
        if source_id != node_id and (source_id, node_id) not in seen:
            seen.add((source_id, node_id))
            edges.append(ArchEdge(source=source_id, target=node_id))
    for v in obj.values():
        _extract_schema_edges(v, source_id, spec, nodes, edges, seen)


# ── AsyncAPI parser ───────────────────────────────────────────────────────────

def _parse_asyncapi(data: Dict) -> Tuple[List[ArchNode], List[ArchEdge]]:
    nodes: Dict[str, ArchNode] = {}
    edges: List[ArchEdge] = []
    seen: Set[Tuple[str, str]] = set()

    # Servers → external nodes
    for server_name, server in (data.get("servers") or {}).items():
        node_id = f"server_{server_name}"
        protocol = server.get("protocol", "") if isinstance(server, dict) else ""
        url = server.get("url", server_name) if isinstance(server, dict) else server_name
        nodes[node_id] = ArchNode(
            id=node_id,
            label=f"{server_name} ({protocol})" if protocol else server_name,
            node_type="external",
        )

    # Channels → queue nodes
    for channel_name, channel in (data.get("channels") or {}).items():
        node_id = f"ch_{channel_name.strip('/').replace('/', '_')}"
        nodes[node_id] = ArchNode(
            id=node_id,
            label=channel_name,
            node_type="queue",
        )

    # Components schemas → data nodes
    for schema_name in (data.get("components", {}).get("schemas") or {}):
        node_id = f"schema_{schema_name}"
        nodes[node_id] = ArchNode(id=node_id, label=f"{schema_name} (schema)", node_type="database")

    return list(nodes.values()), edges


# ── adapter ───────────────────────────────────────────────────────────────────

class OpenAPIAdapter(BaseAdapter):
    source_formats = ["yaml", "yml", "json"]

    def can_handle(self, filename: str, content_peek: bytes) -> bool:
        text = content_peek.decode("utf-8", errors="ignore")
        return (
            "openapi:" in text
            or '"openapi"' in text
            or "swagger:" in text
            or '"swagger"' in text
            or "asyncapi:" in text
            or '"asyncapi"' in text
        )

    def extract(self, content: str | bytes, filename: str = "") -> ArchitectureGraph:
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="replace")

        try:
            data = yaml.safe_load(content)
        except yaml.YAMLError:
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                data = {}

        if not isinstance(data, dict):
            data = {}

        is_asyncapi = "asyncapi" in data
        if is_asyncapi:
            nodes, edges = _parse_asyncapi(data)
            fmt = "asyncapi"
            title = data.get("info", {}).get("title", Path(filename).stem or "asyncapi")
        else:
            nodes, edges = _parse_openapi(data)
            fmt = "openapi"
            title = data.get("info", {}).get("title", Path(filename).stem or "openapi")

        return ArchitectureGraph(
            title=str(title)[:80],
            nodes=nodes,
            edges=edges,
            source_format=fmt,
            adapter_metadata={
                "filename": filename,
                "version": data.get("openapi") or data.get("swagger") or data.get("asyncapi", ""),
                "node_count": len(nodes),
                "edge_count": len(edges),
            },
        )


# Self-register (runs after TF and CF checks — OpenAPI check is on content, not filename)
register(OpenAPIAdapter())
