"""
Platform endpoints — adapter registry + SIP health + agent fleet posture.

GET /api/v1/adapters           — list registered input adapters + supported formats
GET /api/v1/sip/health         — health check for all SIP endpoints
GET /api/v1/agents/fleet-posture — CISO-readable managed agent fleet governance posture
GET /api/v1/agents/tools       — full fleet tool catalog with risk metadata
"""

from __future__ import annotations

from typing import List

from fastapi import APIRouter

router = APIRouter(prefix="/api/v1", tags=["platform"])

_ADAPTER_META = {
    "MermaidAdapter":        {"formats": [".mmd"],                         "description": "Mermaid architecture diagrams — native TA format"},
    "TerraformAdapter":      {"formats": [".tf", "plan.json"],             "description": "Terraform HCL and plan JSON files"},
    "CloudFormationAdapter": {"formats": [".yaml", ".yml", ".json"],       "description": "AWS CloudFormation / CDK synth templates"},
    "OpenAPIAdapter":        {"formats": [".yaml", ".yml", ".json"],       "description": "OpenAPI 3.x and AsyncAPI 2.x specs"},
    "ProseAdapter":          {"formats": [".md", ".txt", ".pdf", ".docx"], "description": "Prose descriptions — LLM-assisted extraction"},
}


@router.get("/adapters")
async def list_adapters():
    """Return all registered input adapters and the artifact formats they handle."""
    try:
        import chatbot.adapters  # noqa: F401  — triggers self-registration
        from chatbot.adapters.registry import list_adapters as _list

        names = _list()
        adapters = []
        for name in names:
            meta = _ADAPTER_META.get(name, {"formats": [], "description": "Custom adapter"})
            adapters.append({
                "name": name,
                "formats": meta["formats"],
                "description": meta["description"],
                "status": "active",
            })
        return {"adapters": adapters, "total": len(adapters)}
    except Exception as exc:
        return {"adapters": [], "total": 0, "error": str(exc)}


@router.get("/sip/health")
async def sip_health():
    """Health check for all TA-SIP endpoints (static, no analysis)."""
    checks = {}

    # Adapter registry
    try:
        import chatbot.adapters  # noqa: F401
        from chatbot.adapters.registry import list_adapters as _list
        checks["adapter_registry"] = {"ok": True, "count": len(_list())}
    except Exception as exc:
        checks["adapter_registry"] = {"ok": False, "error": str(exc)}

    # JSON Schema
    try:
        from pathlib import Path
        import json
        schema_path = Path(__file__).parent.parent.parent / "schemas" / "ta_export_v1.json"
        json.loads(schema_path.read_text())
        checks["ta_export_schema"] = {"ok": True}
    except Exception as exc:
        checks["ta_export_schema"] = {"ok": False, "error": str(exc)}

    # mcp_connector models
    try:
        from mcp_connector.models import TAExportBundle, ComponentContext  # noqa: F401
        checks["mcp_connector_models"] = {"ok": True, "version": "1.1.0"}
    except Exception as exc:
        checks["mcp_connector_models"] = {"ok": False, "error": str(exc)}

    overall = all(v.get("ok", False) for v in checks.values())
    return {"ok": overall, "checks": checks}


@router.get("/agents/fleet-posture")
async def agent_fleet_posture():
    """
    CISO-readable managed agent fleet governance posture.
    Returns tool count, risk distribution, per-agent risk ceiling, write/credential/network
    flags, and any policy conflicts. Posture is CLEAN / WARN / ELEVATED / VIOLATION / EMPTY.
    """
    try:
        from chatbot.agents.managed.tool_registry import get_tool_registry
        from chatbot.agents.managed.registry import get_registry
        posture = get_tool_registry().get_fleet_posture(agent_registry=get_registry())
        return posture
    except Exception as exc:
        return {"posture": "ERROR", "error": str(exc)}


@router.get("/agents/tools")
async def agent_fleet_tools():
    """Full fleet tool catalog — name, risk tier, write/credential/network flags, permitted agents, CSA ART tags."""
    try:
        from chatbot.agents.managed.tool_registry import get_tool_registry
        tools = get_tool_registry().list_tools()
        return {"tools": tools, "total": len(tools)}
    except Exception as exc:
        return {"tools": [], "total": 0, "error": str(exc)}
