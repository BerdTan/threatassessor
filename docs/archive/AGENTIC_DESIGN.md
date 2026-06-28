# ThreatAssessor — Agentic Design

**Status:** Planned — pending implementation  
**Date:** 2026-05-27  
**Scope:** AgentTool enablement, REST job polling, MCP server, API hardening

---

## Overview

Three connected improvements that move ThreatAssessor toward a fully agentic architecture:

1. **AgentTools** — critics call live MITRE lookups during reasoning (eliminates false contradictions)
2. **REST job polling** — submit-then-poll endpoints that decouple submission from result retrieval (blocker for MCP)
3. **MCP server** — exposes the pipeline to Claude Desktop and external agents via the MCP protocol
4. **API hardening** — rate limiting, typed schemas, contract tests

**Dependency order:**

```
AgentTools (independent)
REST job store → MCP server
REST job store → API hardening (typed schemas + contract tests)
```

---

## Phase 1 — AgentTool Enablement

### Current state

- `AgentTool` dataclass + `to_litellm_schema()` exist in `chatbot/modules/agent_framework.py:32–49`
- Tool schemas disabled at `agent_framework.py:135` (commented out, MVP1 flag)
- `_execute_tools()` implemented at `agent_framework.py:403–434`
- Turn-2 re-prompt loop is a stub at lines 156–162 ("not yet implemented in MVP1")

### Tools to enable (priority order)

| Priority | Critic | Tool Name | Wraps |
|---|---|---|---|
| 1 | Tester | `verify_mitre_mapping` | `MitreHelper.get_technique_mitigations(tid)` → checks `mid in result` |
| 2 | Tester | `get_technique_details` | `MitreHelper.find_technique(tid)` → name, tactic, description |
| 3 | Architect | `search_control_context` | stub already exists, calls ARC/ATLAS lookup |
| 4 | Architect | `check_architecture_type` | stub already exists, classifies arch |
| 5 | Red Team | `score_exploit_difficulty` | CVSS-style heuristic on technique + controls |

Start with priorities 1 and 2. They directly prevent the `DATA_REFERENCE_ERROR` class of false contradictions where the Tester denies valid MITRE IDs.

### Changes

**`chatbot/modules/agent_framework.py`**

1. Uncomment tool_schemas at line 135:
   ```python
   tool_schemas = [tool.to_litellm_schema() for tool in self.tools] if self.tools else None
   ```

2. Replace stub (lines 156–162) with a single turn-2 re-prompt loop:
   ```python
   if hasattr(response, 'tool_calls') and response.tool_calls:
       tool_results = self._execute_tools(response.tool_calls)
       tool_msg = "\n".join(
           f"Tool {r['tool']}: {r.get('result', r.get('error', 'failed'))}"
           for r in tool_results
       )
       follow_up = f"{prompt}\n\n[TOOL RESULTS]\n{tool_msg}\n\nContinue your critique using the above tool results."
       response = self.llm_client.generate(
           prompt=follow_up,
           system_message=self.system_prompt,
           model=self.model,
           temperature=0.3,
           max_tokens=4000,
       )
   ```
   Single turn-2 only — no loop (prevents runaway tool calling).

3. Add model compatibility guard:
   ```python
   def _model_supports_tools(self) -> bool:
       model = self.model or os.getenv("LLM_MODEL", "")
       no_tool_prefixes = ("anthropic.claude-v2", "anthropic.claude-instant")
       return not any(model.startswith(p) for p in no_tool_prefixes)
   ```
   Pass `tool_schemas = None` when guard returns False.

**`chatbot/modules/agents/critics/tester_critic.py`**

Add `_verify_mitre_mapping` and `_get_technique_details` as `AgentTool` instances in `TesterCritic.__init__()`, passed to the parent `CriticAgent.__init__(tools=[...])`.

---

## Phase 2 — REST Job Polling Endpoints

### Problem

The MCP server and external agents cannot hold an SSE stream open. They need to submit work and poll for results. Current `/api/v1/analyze-stream` requires a persistent HTTP connection for the full ~30s analysis duration.

### New endpoints

```
POST   /api/v1/jobs/analyze         → {job_id, status: "queued"}
GET    /api/v1/jobs/{job_id}/status → {job_id, status, progress, error}
GET    /api/v1/jobs/{job_id}/result → full analysis result (same shape as /analyze)
DELETE /api/v1/jobs/{job_id}        → cancel + purge
```

### New files

**`chatbot/api/job_store.py`** — in-memory store with 1-hour TTL, thread-safe. No Redis dependency.

Fields per job: `job_id`, `arch_name`, `created_at`, `status` (queued/running/complete/failed/cancelled), `progress` (0–100), `result`, `error`.

**`chatbot/api/routes/jobs.py`** — FastAPI router implementing the four endpoints above. Runs analysis via `asyncio.get_event_loop().run_in_executor()` (same pattern as `/analyze-stream`).

Register in `chatbot/api/app.py`: `app.include_router(jobs_router, prefix="/api/v1")`.

---

## Phase 3 — MCP Server

### Layout

```
mcp_server/
  __init__.py
  server.py       # FastMCP app + 6 tool definitions
  job_client.py   # thin HTTP client wrapping REST job polling endpoints
```

### 6 tools

| Tool | Description |
|---|---|
| `analyze_architecture(file_path)` | Submit arch diagram → returns `job_id` |
| `get_job_status(job_id)` | Poll status: queued → running → complete/failed |
| `get_report(arch_name, file_name)` | Retrieve a report file (default: executive_summary.md) |
| `run_expert_review(arch_name, critic_mode)` | Start MoE review → returns `job_id` |
| `list_architectures()` | List architectures with completed analyses |
| `lookup_mitre(technique_id)` | Look up ATT&CK or ATLAS technique by ID |

`analyze_architecture` and `run_expert_review` use the job polling pattern: submit → return `job_id` → agent calls `get_job_status` until complete.

**Transport:** stdio (standard for Claude Desktop). Start with `python -m mcp_server.server`.  
**Auth:** `TM_API_BASE_URL` and `TM_API_KEY` from environment variables.  
**Dependency:** `mcp` SDK (FastMCP) — add to `requirements.txt`.

---

## Phase 4 — External API Hardening

Five gaps, in priority order:

### 4a. Rate limiting

Add `slowapi` to `requirements.txt`. Key on `TM-API-KEY` header; fall back to client IP.

- Heavy endpoints (`/analyze`, `/analyze-stream`): 10 requests/minute
- Read-only endpoints: 60 requests/minute

### 4b. Typed Pydantic response schemas

Add `AnalysisResult`, `ConfidenceBreakdown`, `TechniqueResult`, `AttackPath`, `ControlRecommendation` to `chatbot/api/models/responses.py`. Replace `Dict[str, Any]` returns in route handlers. Non-breaking for existing consumers.

### 4c. Contract tests

New file `tests/test_api_contract.py` — one test per key endpoint that asserts required fields and types are present. Any schema change breaks the test, making regressions visible immediately.

### 4d. Fix synchronous /analyze blocking the event loop

`POST /api/v1/analyze` calls `service.safe_execute()` synchronously inside an async handler. Replace with `await asyncio.get_event_loop().run_in_executor(None, lambda: service.safe_execute(...))` — same pattern already used in `/analyze-stream`.

### 4e. Deferred (out of scope for now)

- Redis job store (not needed for single-process deployment)
- Per-key quota management UI
- MCP HTTP transport (stdio covers all current use cases)

---

## Files to create / modify

| File | Action | Purpose |
|---|---|---|
| `chatbot/modules/agent_framework.py` | Modify | Uncomment tools; add turn-2 loop; add model guard |
| `chatbot/modules/agents/critics/tester_critic.py` | Modify | Add `verify_mitre_mapping` + `get_technique_details` tools |
| `chatbot/api/job_store.py` | **New** | In-memory job store with TTL |
| `chatbot/api/routes/jobs.py` | **New** | Job CRUD endpoints |
| `chatbot/api/app.py` | Modify | Register jobs router |
| `mcp_server/__init__.py` | **New** | Package init |
| `mcp_server/server.py` | **New** | FastMCP app with 6 tools |
| `mcp_server/job_client.py` | **New** | HTTP client for job polling |
| `requirements.txt` | Modify | Add `mcp`, `slowapi` |
| `chatbot/api/models/responses.py` | Modify | Typed `AnalysisResult` and sub-models |
| `tests/test_api_contract.py` | **New** | Contract tests for key endpoints |

---

## Verification

1. **AgentTools active:** Run Expert Review; tail `logs/api.log` for `"Tester: Executing 1 tool calls"` and `"Tool verify_mitre_mapping: CONFIRMED"`.
2. **Job polling:** `curl -X POST /api/v1/jobs/analyze` → poll until `complete` → `GET /api/v1/jobs/{id}/result`.
3. **MCP starts:** `python -m mcp_server.server` exits cleanly with no import errors.
4. **Rate limit fires:** 11th rapid POST to `/analyze` returns HTTP 429.
5. **Contract tests pass:** `pytest tests/test_api_contract.py` green.
6. **DECISIONS.md:** Add entry after implementation.
