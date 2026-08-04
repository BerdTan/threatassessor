---
name: check-mcp
description: Validate the ThreatAssessor MCP server — imports, tool registration (10 tools), job store, jobs router endpoints, and optional live smoke-test against a running API. No LLM calls. Use after any change to mcp_server/, chatbot/api/job_store.py, or chatbot/api/routes/jobs.py.
allowed-tools: Bash(python3:*) Bash(source:*)
---

# check-mcp — MCP Server Validation + Client Simulator

Validates the full MCP layer (static checks) and optionally runs a live smoke-test
including a real MCP stdio protocol handshake via `client_sim.py`.

## Coverage

| Check | What it verifies |
|-------|-----------------|
| Syntax | All 6 MCP-layer files parse without errors |
| Imports | `mcp.server.fastmcp.FastMCP` importable; `job_client` and `server` load |
| Tool registration | Exactly 10 tools registered with expected names |
| Job store | Create / update / get / TTL-evict all work correctly |
| Jobs router | Both endpoints present, correct HTTP methods and paths |
| App wire-up | `jobs_router` registered in FastAPI app |
| Live REST | Calls REST endpoints directly, checks status codes |
| Live MCP stdio | Full protocol handshake via `client_sim.py --dry-run` |

## Run

```bash
# Static checks only (~3s, no network)
python3 .claude/skills/check-mcp/scripts/check-mcp.py

# Static + live smoke-test (requires running API)
python3 .claude/skills/check-mcp/scripts/check-mcp.py --live

# Live against a specific API URL
python3 .claude/skills/check-mcp/scripts/check-mcp.py --live --url http://localhost:8000
```

## Client Simulator — integration persona reference

`mcp_server/client_sim.py` demonstrates how each client type connects and
chains tools. Useful for onboarding new integrators and testing end-to-end.

```bash
# See all tools (no API needed)
python3 mcp_server/client_sim.py --dry-run

# Run all personas
python3 mcp_server/client_sim.py --all --arch web_app

# Run one persona
python3 mcp_server/client_sim.py --persona soc --arch 21_agentic_ai_system
```

| Persona | Pattern | Use case |
|---------|---------|----------|
| `chatbot` | list → briefing → governance → MITRE | LLM assistant answering security questions |
| `code-agent` | analyze → TATB → governance → gate | GitHub Actions / CI-CD PR gate |
| `ciso` | ciso_brief → tatb corpus | Executive dashboard / Slack digest |
| `soc` | detect_trends → governance → MITRE | SIEM enrichment / Tier-1 triage |
| `copilot` | MITRE lookup + briefing | VS Code / JetBrains inline assistant |
| `chatgpt` | list → briefing → governance | Custom GPT / OpenAI function-calling bridge |

Each persona prints a copy-paste integration snippet (Python or TypeScript) at the end.

## When to use

- After editing `mcp_server/server.py` or `mcp_server/job_client.py`
- After adding or removing MCP tools
- After editing `chatbot/api/job_store.py` or `chatbot/api/routes/jobs.py`
- Before pointing Claude Desktop at the MCP server for the first time
- When onboarding a new integration (run `--dry-run` first, then `--persona <type>`)
