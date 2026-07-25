"""
graph_search.py — GraphRAG query API for TA-Wiz workspace search panel.

GET  /api/v1/graph/query?workspace=<name>&q=<question>
POST /api/v1/graph/refresh?workspace=<name>

The graph is built lazily on first query and cached in memory.
Refresh invalidates the cache for a workspace.
"""

import json
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from chatbot.modules.graph_rag import ThreatGraph

router = APIRouter(prefix="/api/v1/graph", tags=["graph-rag"])

# In-memory cache: workspace_name -> ThreatGraph
_GRAPH_CACHE: dict[str, ThreatGraph] = {}


def _get_report_dir() -> Path:
    from chatbot.config import get_settings
    cfg = get_settings().system.report_dir
    p = Path(cfg)
    return p if p.is_absolute() else Path(__file__).parent.parent.parent.parent / cfg


def _load_workspace_archs(workspace_name: str, report_dir: Path) -> list[str]:
    ws_path = report_dir / ".workspaces.json"
    if not ws_path.exists():
        return []
    try:
        workspaces = json.loads(ws_path.read_text(encoding="utf-8"))
        ws = next((w for w in workspaces if w["name"] == workspace_name), None)
        return ws.get("architectures", []) if ws else []
    except Exception:
        return []


def _get_or_build(workspace_name: str) -> Optional[ThreatGraph]:
    if workspace_name in _GRAPH_CACHE:
        return _GRAPH_CACHE[workspace_name]

    report_dir = _get_report_dir()
    archs = _load_workspace_archs(workspace_name, report_dir)
    if not archs:
        return None

    g = ThreatGraph.build(archs, report_dir)
    _GRAPH_CACHE[workspace_name] = g
    return g


def _missing_archs(g) -> list[str]:
    """Archs declared in the workspace but with no analysis data on disk."""
    return [a for a in g.archs if a not in g.arch_risk_score]


@router.get("/query")
async def graph_query(
    workspace: str = Query(..., description="Workspace name"),
    q: str = Query(..., description="Natural language question"),
) -> JSONResponse:
    """Answer a structural question from the graph without an LLM call.

    Returns:
        {answer: str, from_graph: true, missing_archs: [...]} on a hit
        {answer: null, from_graph: false, missing_archs: [...]} on a miss
    """
    g = _get_or_build(workspace)
    if g is None:
        return JSONResponse({"answer": None, "from_graph": False, "error": "workspace not found"})

    missing = _missing_archs(g)
    answer = g.query(q)
    if answer:
        return JSONResponse({"answer": answer, "from_graph": True, "archs": g.archs, "missing_archs": missing})
    return JSONResponse({"answer": None, "from_graph": False, "missing_archs": missing})


@router.post("/refresh")
async def graph_refresh(workspace: str = Query(...)) -> JSONResponse:
    """Invalidate and rebuild the graph for a workspace."""
    _GRAPH_CACHE.pop(workspace, None)
    g = _get_or_build(workspace)
    if g is None:
        return JSONResponse({"ok": False, "error": "workspace not found"}, status_code=404)
    missing = _missing_archs(g)
    return JSONResponse({
        "ok": True, "archs": g.archs, "missing_archs": missing,
        "attack_paths": len(g.attack_paths), "nodes": len(g.nodes),
    })
