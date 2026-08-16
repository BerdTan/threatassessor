"""
ThreatAssessor MCP Server

Exposes ThreatAssessor capabilities to Claude Desktop and external agents
via the Model Context Protocol (stdio transport).

17 tools:
  1.  analyze_architecture      — submit MMD, get full threat model
  2.  run_expert_review         — queue FULL_MOE, return job_id
  3.  get_job_status            — poll a queued/running job
  4.  get_threat_briefing       — CISO-friendly briefing for a known arch
  5.  get_ciso_brief            — full CISO brief with investment tiers
  6.  get_governance_signals    — AIVSS + injection/evasion signals
  7.  get_detect_trends         — SOC DETECT rule firing trends
  8.  get_tatb_scores           — TATB benchmark scores (corpus or single arch)
  9.  list_architectures        — all analysed architectures + metadata
  10. lookup_mitre_technique    — technique details + recommended mitigations
  11. get_mcp_access_signals    — live session access patterns for DETECT-020/021/022
  12. export_assessment         — unified TA export bundle (ta-export/1.0, OTM-compatible)
  13. governance_check          — fast MMD governance scan, no LLM, returns fired DETECT rules
  14. query_ta_brain            — query Brain patterns: infer threats | list gaps | list patterns
  15. record_brain_feedback     — mark a Brain prediction confirmed/wrong/partial; feeds confidence decay
  16. generate_synthetic_architectures — Generate synthetic MMDs from brain meta-layer gaps; stage for approval
  17. run_taco_agent            — Run TACO routing chain (brain→rag→harness); returns full HopChain

Setup (Claude Desktop):
  {
    "mcpServers": {
      "threatassessor": {
        "command": "python",
        "args": ["-m", "mcp_server.server"],
        "env": {
          "TM_API_BASE_URL": "http://localhost:8000",
          "TM_API_KEY": "your-key-here"
        }
      }
    }
  }
"""

import json
import sys
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env", override=False)

from mcp.server.fastmcp import FastMCP
from mcp_server import job_client as api
from mcp_server.access_logger import get_access_logger

_access_log = get_access_logger()

mcp = FastMCP(
    name="threatassessor",
    instructions=(
        "ThreatAssessor analyses software architecture diagrams (Mermaid .mmd format) "
        "and produces MITRE ATT&CK-mapped threat models, AIVSS scores, SOC detection "
        "signals, and actionable remediation plans. "
        "Use analyze_architecture to submit a new diagram. "
        "Use run_expert_review + get_job_status for deep MoE critic analysis. "
        "Use list_architectures to see what has already been analysed."
    ),
)


# ---------------------------------------------------------------------------
# Tool 1 — analyze_architecture
# ---------------------------------------------------------------------------

@mcp.tool()
def analyze_architecture(
    mmd_content: str,
    ssp_profile: str = "low_risk_cloud",
) -> str:
    """Analyse a Mermaid architecture diagram and return a full threat model.

    Args:
        mmd_content: The full text of the .mmd diagram (Mermaid flowchart syntax).
        ssp_profile: Risk profile — one of: low_risk_cloud, medium_risk_cloud,
                     high_risk_gov, critical_infrastructure. Default: low_risk_cloud.

    Returns:
        JSON with threat findings, MITRE techniques, RAPIDS controls, AIVSS score,
        and confidence breakdown.
    """
    try:
        result = api.analyze_architecture(mmd_content, ssp_profile)
        _access_log.record_tool_call("analyze_architecture")
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("analyze_architecture", success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 2 — run_expert_review
# ---------------------------------------------------------------------------

@mcp.tool()
def run_expert_review(
    arch_name: str,
    critic_mode: str = "partial_parallel",
) -> str:
    """Queue a full MoE expert review (5 critics + ScrumMaster) for an architecture.

    The architecture must already have been analysed (use analyze_architecture first).
    Expert review is async — this tool returns a job_id immediately. Use
    get_job_status(job_id) to poll until status == 'completed'.

    Args:
        arch_name:   Name of the architecture (e.g. 'web_app', 'iot_gateway').
        critic_mode: One of: partial_parallel (recommended), sequential, parallel, auto.

    Returns:
        JSON with job_id, status ('queued'), arch_name, critic_mode.
    """
    try:
        result = api.submit_expert_review(arch_name, critic_mode)
        _access_log.record_tool_call("run_expert_review", arch_name=arch_name)
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("run_expert_review", arch_name=arch_name, success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 3 — get_job_status
# ---------------------------------------------------------------------------

@mcp.tool()
def get_job_status(
    job_id: str,
    wait_for_completion: bool = False,
) -> str:
    """Check the status of a queued or running job.

    Args:
        job_id:               UUID returned by run_expert_review.
        wait_for_completion:  If True, poll until the job finishes (up to 15 minutes).
                              If False (default), return current status immediately.

    Returns:
        JSON with status (queued|running|completed|failed|blocked), progress 0-100,
        message, and result/error when finished.
    """
    try:
        if wait_for_completion:
            result = api.await_job(job_id)
        else:
            result = api.get_job_status(job_id)
        _access_log.record_tool_call("get_job_status")
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("get_job_status", success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 4 — get_threat_briefing
# ---------------------------------------------------------------------------

@mcp.tool()
def get_threat_briefing(
    arch_name: str,
    fmt: str = "md",
) -> str:
    """Get a CISO-ready threat briefing for an analysed architecture.

    Args:
        arch_name: Name of the architecture.
        fmt:       Output format — 'md' (markdown, default) or 'json'.

    Returns:
        Formatted threat briefing with risk summary, top threats, and key controls.
    """
    try:
        result = api.get_threat_briefing(arch_name, fmt)
        _access_log.record_tool_call("get_threat_briefing", arch_name=arch_name)
        if fmt == "md" and isinstance(result, str):
            return result
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("get_threat_briefing", arch_name=arch_name, success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 5 — get_ciso_brief
# ---------------------------------------------------------------------------

@mcp.tool()
def get_ciso_brief(arch_name: str) -> str:
    """Generate a full CISO brief with investment tiers and multi-critic findings.

    Args:
        arch_name: Name of the architecture.

    Returns:
        JSON with executive summary, investment tier breakdown, top findings
        sorted by critic breadth, and a CISO narrative.
    """
    try:
        result = api.get_ciso_brief(arch_name)
        _access_log.record_tool_call("get_ciso_brief", arch_name=arch_name)
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("get_ciso_brief", arch_name=arch_name, success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 6 — get_governance_signals
# ---------------------------------------------------------------------------

@mcp.tool()
def get_governance_signals(arch_name: str) -> str:
    """Get AIVSS score and governance signals for an architecture.

    Signals cover: prompt injection attempts, evasion layers, PII/credential
    leakage, manipulation indicators, and sovereignty compliance.

    Args:
        arch_name: Name of the architecture.

    Returns:
        JSON with AIVSS composite score, severity, per-dimension signals,
        and overall risk level.
    """
    try:
        result = api.get_governance_signals(arch_name)
        _access_log.record_tool_call("get_governance_signals", arch_name=arch_name)
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("get_governance_signals", arch_name=arch_name, success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 7 — get_detect_trends
# ---------------------------------------------------------------------------

@mcp.tool()
def get_detect_trends(arch_name: str) -> str:
    """Get SOC DETECT rule firing trends for an architecture.

    Shows which of the 19 DETECT rules have fired and their trend
    (new | rising | stable | falling | cleared | never) across pipeline runs.

    Args:
        arch_name: Name of the architecture.

    Returns:
        JSON with per-rule trend data, last-fired timestamps, and fire counts.
    """
    try:
        result = api.get_detect_trends(arch_name)
        _access_log.record_tool_call("get_detect_trends", arch_name=arch_name)
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("get_detect_trends", arch_name=arch_name, success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 8 — get_tatb_scores
# ---------------------------------------------------------------------------

@mcp.tool()
def get_tatb_scores(arch_name: str = "") -> str:
    """Get TATB benchmark scores across the corpus or for a single architecture.

    TATB measures four dimensions: Threat-Relevant, TTP-Accurate,
    Risk-Defensible, Plan-Actionable.

    Args:
        arch_name: Filter to a specific architecture name. Empty = full corpus.

    Returns:
        JSON with per-architecture TATB scores and corpus averages.
    """
    try:
        result = api.get_tatb_scores(arch_name)
        _access_log.record_tool_call("get_tatb_scores", arch_name=arch_name)
        if arch_name:
            archs = result.get("architectures", [])
            filtered = [a for a in archs if a.get("name") == arch_name]
            if filtered:
                result = {**result, "architectures": filtered}
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("get_tatb_scores", arch_name=arch_name, success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 9 — list_architectures
# ---------------------------------------------------------------------------

@mcp.tool()
def list_architectures() -> str:
    """List all architectures that have been analysed by ThreatAssessor.

    Returns:
        JSON with architecture names, analysis timestamps, SSP profiles,
        confidence scores, and available report files.
    """
    try:
        result = api.list_architectures()
        _access_log.record_tool_call("list_architectures")
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("list_architectures", success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 10 — lookup_mitre_technique
# ---------------------------------------------------------------------------

@mcp.tool()
def lookup_mitre_technique(technique_ids: str) -> str:
    """Look up MITRE ATT&CK technique details and recommended mitigations.

    Args:
        technique_ids: Comma-separated technique IDs (e.g. 'T1566,T1078,T1059').

    Returns:
        JSON with technique names, descriptions, tactics, and per-technique
        recommended mitigations with mitigation details.
    """
    try:
        result = api.lookup_mitre_technique(technique_ids)
        _access_log.record_tool_call("lookup_mitre_technique")
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("lookup_mitre_technique", success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 11 — get_mcp_access_signals
# ---------------------------------------------------------------------------

@mcp.tool()
def get_mcp_access_signals() -> str:
    """Get the current MCP access pattern signals for this session.

    Returns signals that feed SOC DETECT rules 020–022:
      - recon_sequence:  list_architectures + bulk governance pulls (discovery)
      - job_flood:       expert review submissions without polling back (resource abuse)
      - auth_failures:   repeated 401 responses (credential probing)

    Useful for: SOC dashboards, CI gates, and security-aware agents that want
    to self-monitor for abuse patterns before submitting reports.

    Returns:
        JSON with mcp_access signals dict including severity and flagged status.
    """
    signals = _access_log.get_signals()
    return json.dumps(signals, indent=2)


# ---------------------------------------------------------------------------
# Tool 12 — export_assessment
# ---------------------------------------------------------------------------

@mcp.tool()
def export_assessment(arch_name: str, save: bool = False) -> str:
    """Export a unified TA assessment bundle for an architecture (schema ta-export/1.0).

    The bundle is a single JSON object designed for pipeline consumption:

      gate             — CI/CD result (PASS|BLOCK) + blocking signals
      assessment       — risk scores, attack paths, MITRE techniques, controls
      tatb             — quality benchmark (threat/ttp/risk/plan scores)
      governance       — AIVSS composite + signal summary
      moe_consensus    — critic confidence + redesign signal (if ER ran)
      detect_findings  — OCSF DetectionFinding 2004 events
      security_findings — OCSF SecurityFinding 2001 events
      otm              — OTM-compatible threats / assets / mitigations

    The OTM section makes the bundle importable by Startlift, IriusRisk, and
    other Open Threat Model-compatible tools without a separate converter.

    Args:
        arch_name: Name of the analysed architecture.
        save:      If True, also write ta_export.json to the report directory.

    Returns:
        JSON export bundle (ta-export/1.0).
    """
    try:
        result = api.export_assessment(arch_name, save=save)
        _access_log.record_tool_call("export_assessment", arch_name=arch_name)
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("export_assessment", arch_name=arch_name,
                                     success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 13 — governance_check
# ---------------------------------------------------------------------------

@mcp.tool()
def governance_check(mmd_content: str, arch_name: str = "mcp_input") -> str:
    """Run fast governance checks on raw MMD content without a full analysis.

    Executes check_input() against the submitted Mermaid diagram string and
    returns exploitation, leakage, and sovereignty signals plus any DETECT
    rules that fired — all in ~50ms with no LLM calls.

    Use for:
      - Pre-submission screening of .mmd files before running analyze_architecture
      - CI/CD hooks that want to catch injection, path traversal, or URL injection
      - Security-aware agents that want to self-screen input before forwarding

    Args:
        mmd_content: Raw Mermaid diagram string to screen.
        arch_name:   Optional label for this check (appears in signals).

    Returns:
        JSON with signals dict, fired_rules list, and blocked flag.
        If exploitation.severity == CRITICAL, the response indicates a block.
    """
    try:
        result = api.governance_check(mmd_content, arch_name)
        _access_log.record_tool_call("governance_check")
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("governance_check", success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 14 — query_ta_brain
# ---------------------------------------------------------------------------

@mcp.tool()
def query_ta_brain(
    mode: str = "infer",
    arch_name: str = "",
    topology_signature: str = "",
    arch_type: str = "",
    arch_type_filter: str = "",
) -> str:
    """Query TA Brain — the persistent knowledge graph distilled from the corpus.

    Three modes:

    infer — given an architecture, predict likely threats, missing controls,
      and DETECT rules based on learned patterns from similar architectures.
      Provide arch_name (corpus lookup) OR topology_signature+arch_type (new arch).
      Returns: had_match, confidence, techniques, missing_controls, detect_rules,
               aivss_floor, evidence trace (pattern IDs + source archs).

    gaps — list meta-layer gaps: topology regions where the brain is under-sampled.
      Returns generation prompts for synthetic MMD creation to fill those gaps.

    patterns — list all learned patterns, optionally filtered by arch_type.
      Returns: pattern triggers, predicted techniques, control frequencies, confidence.

    All responses include pattern_version so callers can detect when the brain
    was last rebuilt. Infer queries are logged to ta_brain_interactions.jsonl,
    which feeds the TACO self-improvement loop.

    Args:
        mode:               "infer" | "gaps" | "patterns"
        arch_name:          Corpus architecture name (e.g. "21_agentic_ai_system").
                            Resolves topology_signature and arch_type automatically.
        topology_signature: Direct 16-char topology hash (for architectures not in corpus).
        arch_type:          Architecture type hint when using topology_signature directly.
        arch_type_filter:   Filter patterns by arch_type (patterns mode only).

    Returns:
        JSON response. In infer mode: predictions with confidence and evidence trace.
    """
    try:
        result = api.query_ta_brain(
            mode=mode,
            arch_name=arch_name,
            topology_signature=topology_signature,
            arch_type=arch_type,
            arch_type_filter=arch_type_filter,
        )
        _access_log.record_tool_call("query_ta_brain", arch_name=arch_name or topology_signature)
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("query_ta_brain", success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 15 — record_brain_feedback
# ---------------------------------------------------------------------------

@mcp.tool()
def record_brain_feedback(
    feedback: str,
    arch_name: str = "",
    topology_signature: str = "",
    arch_type: str = "",
    mode: str = "infer",
    reference_ts: str = "",
) -> str:
    """Record feedback on a TA Brain prediction to close the TACO learning loop.

    After receiving a query_ta_brain response, call this tool to signal whether
    the prediction was accurate. Feedback is appended to the interaction log
    (append-only) and propagated to the cache layer immediately:
      confirmed — cache entry strengthened; corpus_confidence raised on next decay run
      wrong     — cache entry evicted; corpus_confidence decayed on next decay run
      partial   — logged only; no cache change

    This feeds Stage 4 (confidence decay) which adjusts pattern confidence between
    brain rebuilds. Patterns that receive consistent wrong feedback lose confidence;
    those confirmed repeatedly gain it.

    Args:
        feedback:           "confirmed" | "wrong" | "partial"
        arch_name:          Corpus architecture name (resolves topology_sig + arch_type).
        topology_signature: Direct topology hash (if arch_name not provided).
        arch_type:          Architecture type (used with topology_signature).
        mode:               Query mode the feedback applies to (default "infer").
        reference_ts:       ISO timestamp of the original query (optional link).

    Returns:
        JSON with recorded, cache_updated, feedback, topology_sig, ts.
    """
    try:
        result = api.record_brain_feedback(
            feedback=feedback,
            arch_name=arch_name,
            topology_signature=topology_signature,
            arch_type=arch_type,
            mode=mode,
            reference_ts=reference_ts,
        )
        _access_log.record_tool_call("record_brain_feedback",
                                     arch_name=arch_name or topology_signature)
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("record_brain_feedback", success=False,
                                     auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 16 — generate_synthetic_architectures
# ---------------------------------------------------------------------------

@mcp.tool()
def generate_synthetic_architectures(
    gap_ids: str = "",
    max_per_run: int = 3,
) -> str:
    """Generate synthetic Mermaid architecture diagrams from TA Brain meta-layer gaps.

    Reads the brain's gap queue (under-sampled topology regions), generates targeted
    MMD diagrams via LLM, and stages them for human approval before harness submission.

    Use this to close the self-growing loop: the brain detects under-sampled regions,
    this tool generates synthetic architectures to fill them, and once approved the
    diagrams run through the full harness to produce new training instances.

    Args:
        gap_ids:     Comma-separated gap IDs to generate for (e.g. "GAP-001,GAP-003").
                     Leave empty to auto-select by priority (forced_gap first).
        max_per_run: Maximum diagrams to generate in this call (default: 3).

    Returns:
        JSON with staged generation results and queue summary.
    """
    try:
        parsed_ids = [g.strip() for g in gap_ids.split(",") if g.strip()] if gap_ids else []
        result = api.generate_synthetic_architectures(
            gap_ids=parsed_ids or None,
            max_per_run=max_per_run,
        )
        _access_log.record_tool_call("generate_synthetic_architectures")
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("generate_synthetic_architectures", success=False,
                                     auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Tool 17 — run_taco_agent
# ---------------------------------------------------------------------------

@mcp.tool()
def run_taco_agent(
    query: str,
    arch_name: str = "",
    force_critic: bool = False,
) -> str:
    """Run the TACO routing chain for a threat question and return the full HopChain.

    TACO routes through: TABrain (pattern KG) → TAWorkspace (graph search) →
    TAHarness (full pipeline, only if confidence < threshold and diagram provided).

    Each hop returns its findings — techniques, missing controls, confidence.
    Use this to ask threat questions about a known architecture and get a
    multi-source answer with routing trace.

    Args:
        query:        Natural-language threat question.
                      e.g. "What are the main risks?" or "Which nodes are exposed?"
        arch_name:    Known corpus architecture name (e.g. "03_aws_3tier").
                      Leave empty for brain-only mode (no workspace graph search).
        force_critic: If True and critic_enabled=true in settings, appends a
                      TACOminiCritic hop reading existing MoE expert review data.

    Returns:
        JSON HopChain with: chain_id, hops (each with hop_type, confidence,
        response_summary, metadata), final_confidence, routing flags.
    """
    try:
        result = api.run_taco_agent(query=query, arch_name=arch_name, force_critic=force_critic)
        _access_log.record_tool_call("run_taco_agent", arch_name=arch_name)
        return json.dumps(result, indent=2)
    except Exception as e:
        auth_failed = "401" in str(e) or "Unauthorized" in str(e)
        _access_log.record_tool_call("run_taco_agent", success=False, auth_failed=auth_failed)
        return json.dumps({"error": str(e)})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse as _ap
    _parser = _ap.ArgumentParser(description="ThreatAssessor MCP Server")
    _parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help=(
            "Transport protocol: stdio (Claude Desktop, default), "
            "sse (legacy HTTP+SSE), "
            "streamable-http (OpenAI Responses API, remote agents)"
        ),
    )
    _parser.add_argument(
        "--host", default="0.0.0.0",
        help="Bind host for sse/streamable-http (default: 0.0.0.0)",
    )
    _parser.add_argument(
        "--port", type=int, default=8001,
        help="Bind port for sse/streamable-http (default: 8001)",
    )
    _args = _parser.parse_args()

    if _args.transport == "stdio":
        mcp.run(transport="stdio")
    else:
        # Network transports require TM_MCP_KEY env var to prevent unauthenticated access.
        # All tool calls still hit the downstream REST API with TM_API_BASE_URL auth,
        # but this adds a transport-level gate before any tool is invoked.
        import os as _os
        _mcp_key = _os.environ.get("TM_MCP_KEY", "")
        if not _mcp_key:
            print(
                "[ThreatAssessor MCP] ERROR: TM_MCP_KEY env var required for network transport.\n"
                "  Set TM_MCP_KEY to a strong secret before starting with --transport sse/streamable-http.",
                flush=True,
            )
            raise SystemExit(1)
        _os.environ.setdefault("FASTMCP_HOST", _args.host)
        _os.environ.setdefault("FASTMCP_PORT", str(_args.port))
        # Pass the key to FastMCP as the bearer token guard
        _os.environ.setdefault("FASTMCP_AUTH_TOKEN", _mcp_key)
        print(f"[ThreatAssessor MCP] {_args.transport} on {_args.host}:{_args.port} (auth: TM_MCP_KEY)", flush=True)
        mcp.run(transport=_args.transport)
