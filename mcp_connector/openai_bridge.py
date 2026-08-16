"""
OpenAI bridge — two integration paths:

1. openai_tools(client)
   Returns a list of OpenAI function-calling tool definitions for all 16
   ThreatAssessor tools. Use with the Chat Completions API (function calling)
   or the Responses API (tools=[...]).

2. openai_mcp_tool(server_url, api_key)
   Returns a single {"type": "mcp"} tool definition that points at a running
   ThreatAssessor MCP server (streamable-http transport). Use with the OpenAI
   Responses API — OpenAI proxies all 16 tools automatically.

Usage — function calling (Chat Completions)::

    from mcp_connector import MCPClient, openai_tools
    from openai import OpenAI

    ta = MCPClient(base_url="http://localhost:8000", api_key="...")
    oai = OpenAI()

    response = oai.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": "Analyse this architecture: ..."}],
        tools=openai_tools(ta),
        tool_choice="auto",
    )

    # Dispatch tool calls back to ThreatAssessor
    for call in (response.choices[0].message.tool_calls or []):
        import json
        fn   = call.function.name
        args = json.loads(call.function.arguments)
        result = getattr(ta, fn)(**args)
        # append result as tool message and continue the loop

Usage — Responses API with remote MCP server (streamable-http)::

    from mcp_connector import openai_mcp_tool
    from openai import OpenAI

    oai = OpenAI()
    response = oai.responses.create(
        model="gpt-4o",
        input="What are the top threats for my_arch?",
        tools=[openai_mcp_tool(
            server_url="https://your-host:8001/mcp",
            api_key="your-ta-key",
        )],
    )
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional


# ── Tool schemas ──────────────────────────────────────────────────────────────
# One entry per MCPClient method. Kept as a module-level constant so callers
# can import and inspect them without instantiating a client.

TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "analyze_architecture",
            "description": (
                "Submit a Mermaid (.mmd) architecture diagram for full threat modelling. "
                "Returns MITRE ATT&CK-mapped attack paths, control recommendations, and "
                "risk scores. Takes ~30 seconds. Use governance_check first to screen the input."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mmd_content": {
                        "type": "string",
                        "description": "Raw Mermaid diagram string (graph LR or flowchart syntax).",
                    },
                    "ssp_profile": {
                        "type": "string",
                        "enum": ["low_risk_cloud", "high_risk_gov", "financial", "healthcare"],
                        "description": "Risk profile affecting control weighting. Default: low_risk_cloud.",
                    },
                },
                "required": ["mmd_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_expert_review",
            "description": (
                "Queue a full MoE expert review (5 critics + ScrumMaster) for an "
                "architecture that has already been analysed. Returns a job_id — "
                "poll with get_job_status until completed."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "arch_name": {"type": "string", "description": "Architecture directory name."},
                    "critic_mode": {
                        "type": "string",
                        "enum": ["partial_parallel", "sequential", "parallel", "auto"],
                        "description": "Execution mode. Default: partial_parallel.",
                    },
                },
                "required": ["arch_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_job_status",
            "description": "Poll the status of a queued or running expert review job.",
            "parameters": {
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "UUID from run_expert_review."},
                    "wait_for_completion": {
                        "type": "boolean",
                        "description": "Block until completed or failed. Default: false.",
                    },
                },
                "required": ["job_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_threat_briefing",
            "description": "Get a CISO-ready threat briefing for an analysed architecture.",
            "parameters": {
                "type": "object",
                "properties": {
                    "arch_name": {"type": "string"},
                    "fmt": {
                        "type": "string",
                        "enum": ["md", "json"],
                        "description": "md (default, markdown) or json.",
                    },
                },
                "required": ["arch_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_ciso_brief",
            "description": (
                "Generate a full CISO brief with investment tiers (quick-win / recommended / maximum), "
                "multi-critic corroborated findings, and a risk waterfall."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "arch_name": {"type": "string"},
                },
                "required": ["arch_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_governance_signals",
            "description": (
                "Get AIVSS composite score and per-dimension governance signals "
                "(exploitation, manipulation, leakage, sovereignty). "
                "Shows injection/evasion detections and outbound risk."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "arch_name": {"type": "string"},
                },
                "required": ["arch_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_detect_trends",
            "description": (
                "Get SOC DETECT rule firing trends across pipeline runs for an architecture. "
                "Trend values: new | rising | stable | falling | cleared | never. "
                "Covers all 24 DETECT rules."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "arch_name": {"type": "string"},
                },
                "required": ["arch_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_tatb_scores",
            "description": (
                "Get TATB (TA Test Benchmark) quality scores. "
                "Four dimensions: threat_relevant, ttp_accurate, risk_defensible, plan_actionable. "
                "Pass arch_name for a single architecture, omit for the full corpus."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "arch_name": {
                        "type": "string",
                        "description": "Architecture name. Omit for corpus-wide scores.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_architectures",
            "description": "List all architectures that have been analysed, with metadata.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "lookup_mitre_technique",
            "description": (
                "Look up MITRE ATT&CK technique details and recommended mitigations. "
                "Returns tactic, platform, description, and mapped M-codes."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "technique_ids": {
                        "type": "string",
                        "description": "Comma-separated ATT&CK IDs, e.g. 'T1190,T1078,T1059'.",
                    },
                },
                "required": ["technique_ids"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_mcp_access_signals",
            "description": (
                "Get live MCP session access pattern signals. "
                "Shows recon_sequence, job_flood, and auth_failures signals "
                "that feed SOC DETECT rules 020–022."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "export_assessment",
            "description": (
                "Export a unified TA assessment bundle (schema ta-export/1.0). "
                "Single JSON with gate (PASS|BLOCK for CI/CD), attack paths, TATB scores, "
                "OCSF findings, and OTM-compatible threats/mitigations. "
                "Check bundle['gate']['result'] == 'BLOCK' to halt a pipeline."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "arch_name": {"type": "string"},
                    "save": {
                        "type": "boolean",
                        "description": "Write ta_export.json to the report directory. Default: false.",
                    },
                },
                "required": ["arch_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "governance_check",
            "description": (
                "Screen raw Mermaid MMD content for injection, path traversal, external URLs, "
                "and evasion homoglyphs in ~50ms (no LLM). "
                "Returns fired DETECT rule IDs and blocked=true on CRITICAL input. "
                "Call this before analyze_architecture to pre-screen untrusted diagrams."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mmd_content": {
                        "type": "string",
                        "description": "Raw Mermaid diagram string to screen.",
                    },
                    "arch_name": {
                        "type": "string",
                        "description": "Optional label for this check.",
                    },
                },
                "required": ["mmd_content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_ta_brain",
            "description": (
                "Query TA Brain — the persistent knowledge graph distilled from the corpus. "
                "Mode 'infer': predict threats, missing controls, and DETECT rules for an arch. "
                "Mode 'gaps': list under-sampled topology regions. "
                "Mode 'patterns': list all learned patterns."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": ["infer", "gaps", "patterns"],
                        "description": "Query mode. Default: infer.",
                    },
                    "arch_name": {
                        "type": "string",
                        "description": "Corpus architecture name (resolves topology + arch_type automatically).",
                    },
                    "topology_signature": {
                        "type": "string",
                        "description": "Direct 16-char topology hash for architectures not in corpus.",
                    },
                    "arch_type": {
                        "type": "string",
                        "description": "Architecture type hint when using topology_signature directly.",
                    },
                    "arch_type_filter": {
                        "type": "string",
                        "description": "Filter patterns by arch_type (patterns mode only).",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "record_brain_feedback",
            "description": (
                "Record feedback on a TA Brain prediction to close the TACO learning loop. "
                "'confirmed' strengthens the pattern; 'wrong' decays confidence and evicts cache; "
                "'partial' logs without changing confidence."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "feedback": {
                        "type": "string",
                        "enum": ["confirmed", "wrong", "partial"],
                        "description": "Verdict on the Brain prediction.",
                    },
                    "arch_name": {
                        "type": "string",
                        "description": "Corpus architecture name.",
                    },
                    "topology_signature": {
                        "type": "string",
                        "description": "Direct topology hash (if arch_name not provided).",
                    },
                    "arch_type": {"type": "string"},
                    "mode": {
                        "type": "string",
                        "description": "Query mode the feedback applies to. Default: infer.",
                    },
                    "reference_ts": {
                        "type": "string",
                        "description": "ISO timestamp of the original query (optional link).",
                    },
                },
                "required": ["feedback"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "generate_synthetic_architectures",
            "description": (
                "Generate synthetic Mermaid architecture diagrams from TA Brain meta-layer gaps. "
                "Stages diagrams for human approval before harness submission. "
                "Use to close the self-growing Brain loop."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "gap_ids": {
                        "type": "string",
                        "description": "Comma-separated gap IDs (e.g. 'GAP-001,GAP-003'). Empty = auto-select.",
                    },
                    "max_per_run": {
                        "type": "integer",
                        "description": "Maximum diagrams to generate. Default: 3.",
                    },
                },
            },
        },
    },
]


# ── Public API ────────────────────────────────────────────────────────────────

def openai_tools(client: Optional[Any] = None) -> List[Dict[str, Any]]:
    """Return OpenAI Chat Completions function-calling tool definitions for all 16 tools.

    The returned list is passed directly to client.chat.completions.create(tools=...).
    Pass the MCPClient instance if you want tool calls auto-dispatched (future use).

    Args:
        client: Optional MCPClient (unused currently; reserved for auto-dispatch).

    Returns:
        List of OpenAI tool definition dicts.
    """
    return TOOL_DEFINITIONS


def openai_mcp_tool(
    server_url: str,
    api_key: str = "",
    require_approval: str = "never",
    allowed_tools: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return an OpenAI Responses API MCP tool definition pointing at a remote server.

    The ThreatAssessor MCP server must be running with streamable-http transport:
        python -m mcp_server.server --transport streamable-http --port 8001

    OpenAI will proxy all 16 tools automatically — no individual function definitions needed.

    Args:
        server_url:       Full URL of the MCP server, e.g. 'https://your-host:8001/mcp'.
        api_key:          TM-API-KEY value (passed as Authorization header to the MCP server).
        require_approval: 'never' (default) or a dict of {never: {tool_names: [...]}} for granular control.
        allowed_tools:    Subset of tool names to expose. None = all 16 tools.

    Returns:
        OpenAI Responses API tool dict with type='mcp'.

    Example::

        from openai import OpenAI
        from mcp_connector import openai_mcp_tool

        oai = OpenAI()
        response = oai.responses.create(
            model="gpt-4o",
            input="What are the top threats for my_arch?",
            tools=[openai_mcp_tool("https://ta.example.com:8001/mcp", api_key="secret")],
        )
    """
    tool: Dict[str, Any] = {
        "type": "mcp",
        "server_label": "threatassessor",
        "server_url": server_url,
        "require_approval": require_approval,
    }
    if api_key:
        tool["authorization"] = api_key
    if allowed_tools:
        tool["allowed_tools"] = allowed_tools
    return tool
