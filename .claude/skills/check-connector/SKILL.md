name: check-connector
description: Validate the ThreatAssessor connector layer — mcp_connector package integrity, OpenAI tool definitions (13 tools), openai_mcp_tool shape, LangChain bridge graceful import, OpenAPI spec (47 paths, auth), --transport flag, and live MCPClient calls (governance_check, export_assessment, tatb). Use after any change to mcp_connector/, openapi.yaml, or mcp_server/server.py.
allowed-tools: Bash(python3:*)

# check-connector — Connector Layer Validation

Validates `mcp_connector/`, `openapi.yaml`, and the `--transport` flag on `mcp_server/server.py`.
Does not re-check the MCP server internals (use `/check-mcp` for that).

## Coverage

| Section | What it verifies |
|---------|-----------------|
| Package structure | All 6 files present and parseable |
| Imports | MCPClient, openai_bridge, langchain_bridge load cleanly |
| OpenAI tool defs | 13 defs, required fields, all names match server |
| OpenAI MCP tool | `{"type":"mcp"}` shape, authorization, allowed_tools filtering |
| LangChain bridge | Graceful ImportError without langchain; BaseTool list when installed |
| OpenAPI spec | ≥40 paths, ApiKeyHeader, global security, /health no-auth, x-mcp-server hint |
| Transport flag | --transport stdio/sse/streamable-http in --help, --host/--port present |
| Live MCPClient | list_architectures, governance_check (benign + injection), export_assessment, get_tatb_scores |

## Run

```bash
# Static + live (API must be running)
python3 .claude/skills/check-connector/scripts/check-connector.py

# Static only (no API needed, ~2s)
python3 .claude/skills/check-connector/scripts/check-connector.py --static

# Custom URL / arch
python3 .claude/skills/check-connector/scripts/check-connector.py --url http://host:8000 --arch my_arch
```

## Integration patterns (from mcp_connector/README.md)

| Pattern | File | Key function |
|---------|------|-------------|
| Claude Desktop (stdio) | `mcp_server/server.py` | `mcp.run(transport="stdio")` — zero config |
| OpenAI Responses API | `mcp_connector/openai_bridge.py` | `openai_mcp_tool(server_url=...)` |
| OpenAI Chat Completions | `mcp_connector/openai_bridge.py` | `openai_tools()` → 13 function defs |
| LangChain | `mcp_connector/langchain_bridge.py` | `langchain_tools(client)` → 11 BaseTool |
| Direct Python | `mcp_connector/client.py` | `MCPClient(base_url=..., api_key=...)` |
| n8n / REST | `openapi.yaml` / `/openapi.json` | 47 documented paths |

## Starting the HTTP transport (for OpenAI Responses API)

```bash
# streamable-http — recommended for remote agents (OpenAI, LangChain, CI runners)
python -m mcp_server.server --transport streamable-http --port 8001

# sse — legacy HTTP+SSE for older MCP clients
python -m mcp_server.server --transport sse --port 8001
```

Then in OpenAI:
```python
from mcp_connector import openai_mcp_tool
tools = [openai_mcp_tool("http://your-host:8001/mcp", api_key="your-ta-key")]
```

## When to use

- After editing `mcp_connector/` (any file)
- After regenerating `openapi.yaml`
- After adding or removing MCP tools (also run `/check-mcp`)
- Before publishing the connector package or pointing an external agent at the HTTP server
