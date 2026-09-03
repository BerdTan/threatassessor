"""
threatassessor-mcp — Python connector for ThreatAssessor MCP server.

Provides:
  MCPClient          — typed Python wrapper for all 17 MCP tools (REST-based)
  openai_tools()     — pre-built OpenAI Responses API tool definitions
  langchain_tools()  — LangChain BaseTool wrappers
  openai_mcp_tool()  — single MCP tool definition for OpenAI Responses API
                       (points at a running streamable-http server)
"""
from mcp_connector.client import MCPClient
from mcp_connector.openai_bridge import openai_tools, openai_mcp_tool
from mcp_connector.langchain_bridge import langchain_tools
from mcp_connector.models import (
    TAExportBundle, GateResult, AttackPath, AssessmentSection,
    TATBSection, GovernanceSection, OTMSection, MoEConsensus,
    ComponentContext,
)

__all__ = [
    "MCPClient", "openai_tools", "openai_mcp_tool", "langchain_tools",
    "TAExportBundle", "GateResult", "AttackPath", "AssessmentSection",
    "TATBSection", "GovernanceSection", "OTMSection", "MoEConsensus",
    "ComponentContext",
]
__version__ = "1.1.0"
