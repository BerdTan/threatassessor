"""
ThreatAssessor MCP Server

Exposes ThreatAssessor capabilities to Claude Desktop and external agents
via the Model Context Protocol (stdio transport).

13 tools:
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
        # For remote transports, set host/port via env vars that FastMCP reads
        import os as _os
        _os.environ.setdefault("FASTMCP_HOST", _args.host)
        _os.environ.setdefault("FASTMCP_PORT", str(_args.port))
        print(f"[ThreatAssessor MCP] {_args.transport} on {_args.host}:{_args.port}", flush=True)
        mcp.run(transport=_args.transport)
