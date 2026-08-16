# ThreatAssessor MCP Server

Exposes ThreatAssessor to Claude Desktop and external agents via the Model Context Protocol (stdio transport).

## What's in this directory

```
mcp_server/
  server.py       — FastMCP app, 16 tool definitions
  job_client.py   — thin HTTP wrapper (all REST calls go through here)
  client_sim.py   — integration persona simulator (testing + onboarding)
  README.md       — this file
```

---

## Prerequisites

### 1. Python environment

```bash
# From the repo root
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # includes mcp>=1.0.0
```

### 2. Environment variables

Copy `.env.example` to `.env` and fill in at minimum:

```bash
API_KEY=your-api-key-here          # used by the REST API
TM_API_KEY=your-api-key-here       # used by the MCP server when calling the REST API
TM_API_BASE_URL=http://localhost:8000   # default, change if API runs elsewhere
```

`TM_API_KEY` and `API_KEY` must be the same value — `TM_API_KEY` is what the MCP server
sends as the `TM-API-KEY` header to the REST API.

### 3. ThreatAssessor REST API

The MCP server is a thin wrapper — it calls the REST API for everything. The API must be running before any tool calls work.

```bash
# Start
./scripts/api/api_start.sh

# Check it's up
./scripts/api/api_status.sh

# Or check manually
curl http://localhost:8000/health
```

---

## Testing before connecting a client

Run these steps in order. Each step catches a different failure class.

### Step 1 — Static validation (no API needed, ~3s)

Verifies syntax, imports, tool registration, job store, router, and app wiring.

```bash
.venv/bin/python3 .claude/skills/check-mcp/scripts/check-mcp.py
```

Expected: `PASS  30/30 checks passed`

### Step 2 — Protocol dry-run (no API needed, ~5s)

Spawns `server.py` as a subprocess and does a real MCP `initialize` handshake over stdio.
Confirms the server starts cleanly and all 10 tools negotiate correctly.

```bash
.venv/bin/python3 mcp_server/client_sim.py --dry-run
```

Expected: `✓  Server: threatassessor  v...` and 10 tools listed with args.

### Step 3 — Live REST + MCP validation (API must be running)

Checks REST endpoints respond correctly, then repeats the MCP dry-run.

```bash
./scripts/api/api_start.sh   # if not already running
.venv/bin/python3 .claude/skills/check-mcp/scripts/check-mcp.py --live
```

### Step 4 — Full persona simulation (API must be running, arch must exist)

Runs all 6 client personas end-to-end with real tool calls. Pick an architecture
name that already has a report (use `list_architectures` or `ls report/`).

```bash
.venv/bin/python3 mcp_server/client_sim.py --all --arch web_app
```

Or run one persona:

```bash
.venv/bin/python3 mcp_server/client_sim.py --persona soc --arch web_app
```

---

## Client integration patterns

`client_sim.py` demonstrates exactly how each client type should use the tools.
Run `--dry-run` first to verify setup, then the relevant persona.

| Persona | Tool chain | Use case | Snippet language |
|---------|-----------|----------|-----------------|
| `chatbot` | list → briefing → governance → MITRE | LLM assistant | Python |
| `code-agent` | TATB + governance → gate | GitHub Actions / CI gate | Python + YAML |
| `ciso` | CISO brief → TATB corpus | Executive dashboard / Slack digest | Python |
| `soc` | DETECT trends → governance → MITRE | SIEM enrichment / Tier-1 triage | Python |
| `copilot` | MITRE lookup + briefing | VS Code / JetBrains extension | TypeScript |
| `chatgpt` | list → briefing → governance | Custom GPT / OpenAI function-calling | Python |

Each persona prints a copy-paste integration snippet at the end of its run.

---

## Claude Desktop setup

Once steps 1–3 above pass, add to your Claude Desktop config:

**macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "threatassessor": {
      "command": "/absolute/path/to/DEV-TEST/.venv/bin/python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/DEV-TEST",
      "env": {
        "TM_API_BASE_URL": "http://localhost:8000",
        "TM_API_KEY": "your-api-key-here"
      }
    }
  }
}
```

Restart Claude Desktop after saving. You should see "threatassessor" in the MCP tools panel.

**Troubleshooting:**
- If tools don't appear: check Claude Desktop logs (`~/Library/Logs/Claude/` on macOS)
- If tools return errors: confirm the REST API is running (`./scripts/api/api_status.sh`)
- If auth fails: verify `TM_API_KEY` matches `API_KEY` in `.env`
- Run step 2 (dry-run) first to isolate server-side vs client-side issues

---

## Other clients (non-Claude Desktop)

### Python (any MCP-compatible agent)

```python
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
import asyncio, json

params = StdioServerParameters(
    command="/path/to/.venv/bin/python",
    args=["-m", "mcp_server.server"],
    cwd="/path/to/DEV-TEST",
    env={"TM_API_BASE_URL": "http://localhost:8000", "TM_API_KEY": "..."},
)

async def main():
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            result = await session.call_tool(
                "list_architectures", arguments=None
            )
            print(result.content[0].text)

asyncio.run(main())
```

### TypeScript / Node.js (VS Code extension, Copilot, etc.)

```typescript
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const transport = new StdioClientTransport({
  command: "python",
  args: ["-m", "mcp_server.server"],
  cwd: "/path/to/DEV-TEST",
  env: { TM_API_BASE_URL: "http://localhost:8000", TM_API_KEY: "..." },
});
const client = new Client({ name: "my-extension", version: "1.0" }, {});
await client.connect(transport);

const result = await client.callTool({
  name: "lookup_mitre_technique",
  arguments: { technique_ids: "T1190,T1078" },
});
console.log(result.content[0].text);
```

### OpenAI / ChatGPT function-calling bridge

The MCP tools map directly to OpenAI function definitions via `list_tools()`:

```python
mcp_tools = await session.list_tools()
openai_functions = [
    {
        "name": t.name,
        "description": t.description,
        "parameters": t.inputSchema,
    }
    for t in mcp_tools.tools
]
# Pass openai_functions to your OpenAI chat completion call.
# When the model calls a function, execute it via:
mcp_result = await session.call_tool(fn_call.name, json.loads(fn_call.arguments))
```

---

## The 10 tools

| Tool | Args | Sync? | What it returns |
|------|------|-------|----------------|
| `analyze_architecture` | `mmd_content`, `ssp_profile` | Yes (~30s) | Full threat model + MITRE TTPs + AIVSS score |
| `run_expert_review` | `arch_name`, `critic_mode` | No → job_id | `{job_id, status: queued}` |
| `get_job_status` | `job_id`, `wait_for_completion` | Poll / block | `{status, progress, result?}` |
| `get_threat_briefing` | `arch_name`, `fmt` | Yes | CISO briefing (md or json) |
| `get_ciso_brief` | `arch_name` | Yes | Executive brief + investment tiers |
| `get_governance_signals` | `arch_name` | Yes | AIVSS composite + per-signal breakdown |
| `get_detect_trends` | `arch_name` | Yes | Per-rule firing trend + fire counts |
| `get_tatb_scores` | `arch_name` (optional) | Yes | TATB dimension scores |
| `list_architectures` | _(none)_ | Yes | All analysed archs + metadata |
| `lookup_mitre_technique` | `technique_ids` | Yes | Technique details + mitigations |

### Expert review async flow

```
run_expert_review(arch_name)        → {job_id: "abc-123", status: "queued"}
get_job_status(job_id)              → {status: "running", progress: 42}
get_job_status(job_id)              → {status: "running", progress: 78}
get_job_status(job_id)              → {status: "completed", progress: 100, result: {...}}

# Or block in one call:
get_job_status(job_id, wait_for_completion=True)   → completed result
```

Jobs expire after 1 hour. The in-memory store resets on API restart.
Report files written to `report/{arch_name}/` persist across restarts.

---

## New REST endpoints (added for MCP)

- `POST /api/v1/jobs/expert-review` — `{arch_name, critic_mode}` → `{job_id, status}`
- `GET  /api/v1/jobs/{job_id}/status` — `{status, progress, message, result?, error?}`

These endpoints are also accessible directly if you prefer REST over MCP.
