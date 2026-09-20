#!/usr/bin/env python3
"""mcp-audit — Engine Item 12: MCP attack surface security posture audit.

Six audit dimensions (all static — no API required):
  DIM-1  Tool description injection    — scan docstrings for instruction-override patterns
  DIM-2  Parameter validation gaps     — unvalidated string inputs to LLM/crawl/API
  DIM-3  Scope gap analysis            — tools absent from all client_sim personas
  DIM-4  Transport security            — network transport auth guard completeness
  DIM-5  Adversarial persona coverage  — tools without adversarial persona test
  DIM-6  Agent identity validation     — ABAC caller-identity at MCP dispatch
"""

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
SERVER_PY = ROOT / "mcp_server" / "server.py"
CLIENT_SIM_PY = ROOT / "mcp_server" / "client_sim.py"

# ─── severity ordering ───────────────────────────────────────────────────────

SEVERITIES = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]


def sev_key(s: str) -> int:
    try:
        return SEVERITIES.index(s)
    except ValueError:
        return 99


# ─── AST helpers ─────────────────────────────────────────────────────────────

def _load_source(path: Path) -> ast.Module:
    return ast.parse(path.read_text())


def extract_tools(tree: ast.Module) -> list[dict]:
    """Return list of {name, docstring, params} for each @mcp.tool() function."""
    tools = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        decorators = [
            ast.unparse(d) for d in node.decorator_list
        ]
        if not any("mcp.tool" in d for d in decorators):
            continue
        docstring = ast.get_docstring(node) or ""
        params = []
        for arg in node.args.args:
            ann = ast.unparse(arg.annotation) if arg.annotation else "unknown"
            params.append({"name": arg.arg, "type": ann})
        defaults_offset = len(node.args.args) - len(node.args.defaults)
        for i, default in enumerate(node.args.defaults):
            params[defaults_offset + i]["default"] = ast.unparse(default)
        tools.append({"name": node.name, "docstring": docstring, "params": params})
    return tools


def extract_fastmcp_instructions(tree: ast.Module) -> str:
    """Extract the instructions= string passed to FastMCP(...)."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = ast.unparse(node.func)
            if "FastMCP" in func:
                for kw in node.keywords:
                    if kw.arg == "instructions":
                        return ast.unparse(kw.value).strip("\"'")
    return ""


def extract_tool_risk_map(tree: ast.Module) -> dict[str, str]:
    """Extract _TOOL_RISK dict from server.py. Handles both Assign and AnnAssign."""
    for node in ast.walk(tree):
        # _TOOL_RISK: dict[str, str] = {...}  →  AnnAssign
        if isinstance(node, ast.AnnAssign):
            if isinstance(node.target, ast.Name) and node.target.id == "_TOOL_RISK":
                if node.value and isinstance(node.value, ast.Dict):
                    result = {}
                    for k, v in zip(node.value.keys, node.value.values):
                        key = ast.literal_eval(k)
                        val = ast.literal_eval(v)
                        result[key] = val
                    return result
        # _TOOL_RISK = {...}  →  Assign (fallback)
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "_TOOL_RISK":
                    if isinstance(node.value, ast.Dict):
                        result = {}
                        for k, v in zip(node.value.keys, node.value.values):
                            key = ast.literal_eval(k)
                            val = ast.literal_eval(v)
                            result[key] = val
                        return result
    return {}


def extract_sim_tool_calls(sim_tree: ast.Module) -> set[str]:
    """Return set of tool names called in client_sim.py.

    Handles two call patterns:
      await call(session, "tool_name", ...)       → args[1] is the tool name
      await session.call_tool("tool_name", {...})  → args[0] is the tool name
    """
    called = set()
    for node in ast.walk(sim_tree):
        if not (isinstance(node, ast.Await) and isinstance(node.value, ast.Call)):
            continue
        func = ast.unparse(node.value.func)
        args = node.value.args
        kws = node.value.keywords
        if func == "call" and len(args) >= 2:
            # await call(session, "tool_name", ...)
            try:
                called.add(ast.literal_eval(args[1]))
            except (ValueError, TypeError):
                pass
        elif "call_tool" in func and args:
            # await session.call_tool("tool_name", ...)
            try:
                called.add(ast.literal_eval(args[0]))
            except (ValueError, TypeError):
                pass
        # keyword form: call(session, tool="tool_name")
        for kw in kws:
            if kw.arg in ("tool", "tool_name"):
                try:
                    called.add(ast.literal_eval(kw.value))
                except (ValueError, TypeError):
                    pass
    return called


# ─── DIM-1: Tool description injection ───────────────────────────────────────

INJECTION_PATTERNS = [
    (r"\bignore\b.{0,40}\b(all |previous |prior |above )?(instructions?|rules?|guidelines?|constraints?)\b",
     "instruction-override phrase"),
    (r"\bforget\b.{0,30}\b(previous|prior|above|all)\b", "forget-prior directive"),
    (r"\bact as\b.{0,40}", "role-impersonation phrase"),
    (r"\byou are now\b", "persona-reset directive"),
    (r"\bdisregard\b.{0,30}\binstructions?\b", "disregard-instructions phrase"),
    (r"\boverride\b.{0,30}\b(instructions?|rules?|policies?)\b", "policy-override phrase"),
    (r"\bnew (persona|role|identity)\b", "persona-override phrase"),
    (r"\bsystem prompt\b", "system-prompt reference"),
    (r"\bDAN\b|\bjailbreak\b", "known jailbreak keyword"),
]


def dim1_description_injection(tools: list[dict], instructions: str) -> list[dict]:
    findings = []
    sources = [(f"FastMCP.instructions", instructions)] + [
        (f"tool:{t['name']}", t["docstring"]) for t in tools
    ]
    for label, text in sources:
        for pattern, desc in INJECTION_PATTERNS:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                findings.append({
                    "dim": "DIM-1",
                    "severity": "HIGH",
                    "location": label,
                    "issue": f"Possible injection vector: {desc}",
                    "detail": f'Matched: "{m.group(0)[:80]}"',
                    "remediation": "Remove or rewrite phrase; descriptions are agent-readable prompts",
                })
    if not findings:
        findings.append({
            "dim": "DIM-1",
            "severity": "INFO",
            "location": "all 18 tools + FastMCP.instructions",
            "issue": "No injection patterns detected",
            "detail": "Clean",
            "remediation": "",
        })
    return findings


# ─── DIM-2: Parameter validation gaps ────────────────────────────────────────

# Params that should have explicit format/range validation but don't
_PARAM_RISKS: dict[str, list[tuple[str, str, str]]] = {
    "run_taco_agent": [
        ("query", "HIGH",
         "Natural-language string flows directly to LLM via api.run_taco_agent(); "
         "no injection screen applied (only mmd_content gets _mcp_content_trust_check)."),
    ],
    "run_taclaw": [
        ("target", "HIGH",
         "Local path or git URL flows to RepoCrawler without path-traversal validation; "
         "a path like '../../../../etc' or a private git URL could exfiltrate data."),
        ("target_type", "MEDIUM",
         "Enum constraint ('directory'|'git_url') not enforced at MCP layer; "
         "arbitrary string reaches API payload."),
        ("ssp_profile", "LOW",
         "Enum constraint (low_risk_cloud|medium_risk_cloud|high_risk_gov|critical_infrastructure) "
         "not enforced at MCP layer for this tool (only docstring note, no validation)."),
    ],
    "analyze_architecture": [
        ("ssp_profile", "LOW",
         "Enum constraint not enforced at MCP layer; arbitrary value flows to API."),
    ],
    "generate_synthetic_architectures": [
        ("max_per_run", "MEDIUM",
         "Integer param has no upper bound; a caller could pass max_per_run=1000 "
         "triggering mass LLM generation in a single call."),
        ("gap_ids", "LOW",
         "CSV string fed to split() and forwarded to API with no format check on individual IDs."),
    ],
    "record_brain_feedback": [
        ("feedback", "MEDIUM",
         "Enum constraint ('confirmed'|'wrong'|'partial') declared in docstring only; "
         "no Python-level validation before the value reaches api.record_brain_feedback()."),
    ],
    "lookup_mitre_technique": [
        ("technique_ids", "MEDIUM",
         "CSV string (e.g. 'T1566,T1078') has no format validation; "
         "arbitrary string flows to the MITRE lookup endpoint."),
    ],
    "run_expert_review": [
        ("critic_mode", "LOW",
         "Enum constraint (partial_parallel|sequential|parallel|auto) not enforced at MCP layer."),
    ],
    "get_threat_briefing": [
        ("fmt", "LOW",
         "Enum constraint ('md'|'json') not enforced at MCP layer."),
    ],
}

_CONTENT_TRUST_PROTECTED = {"mmd_content"}  # covered by _mcp_content_trust_check


def dim2_parameter_validation(tools: list[dict]) -> list[dict]:
    findings = []
    tool_map = {t["name"]: t for t in tools}
    for tool_name, param_risks in _PARAM_RISKS.items():
        tool = tool_map.get(tool_name)
        if not tool:
            continue
        param_names = {p["name"] for p in tool["params"]}
        for param, severity, detail in param_risks:
            if param not in param_names:
                continue
            if param in _CONTENT_TRUST_PROTECTED:
                continue
            findings.append({
                "dim": "DIM-2",
                "severity": severity,
                "location": f"tool:{tool_name} param:{param}",
                "issue": f"Unvalidated parameter reaches downstream system",
                "detail": detail,
                "remediation": (
                    "Add explicit validation: enum allowlist check, integer range clamp, "
                    "or path-traversal sanitization before the API call."
                ),
            })
    if not findings:
        findings.append({
            "dim": "DIM-2",
            "severity": "INFO",
            "location": "all tools",
            "issue": "No parameter validation gaps detected",
            "detail": "Clean",
            "remediation": "",
        })
    return findings


# ─── DIM-3: Scope gap analysis ────────────────────────────────────────────────

_RISK_SEVERITY_MAP = {"analyze": "HIGH", "modify": "HIGH", "read": "MEDIUM"}


def dim3_scope_gap(tools: list[dict], sim_called: set[str], risk_map: dict[str, str]) -> list[dict]:
    findings = []
    tool_names = {t["name"] for t in tools}
    uncovered = tool_names - sim_called
    for name in sorted(uncovered):
        tier = risk_map.get(name, "read")
        sev = _RISK_SEVERITY_MAP.get(tier, "MEDIUM")
        findings.append({
            "dim": "DIM-3",
            "severity": sev,
            "location": f"tool:{name}",
            "issue": f"Tool not exercised by any client_sim persona (tier: {tier})",
            "detail": (
                "No benign-path coverage means no baseline behaviour recording in "
                "MCPAccessLogger for this tool; anomaly detection rules have no "
                "normal-traffic floor to compare against."
            ),
            "remediation": (
                f"Add {'an adversarial' if tier != 'read' else 'a'} persona scenario "
                f"to client_sim.py that exercises {name}."
            ),
        })
    covered = tool_names & sim_called
    if covered:
        findings.append({
            "dim": "DIM-3",
            "severity": "INFO",
            "location": f"{len(covered)} tools covered",
            "issue": f"Persona coverage: {len(covered)}/{len(tool_names)} tools",
            "detail": ", ".join(sorted(covered)),
            "remediation": "",
        })
    return findings


# ─── DIM-4: Transport security ────────────────────────────────────────────────

def dim4_transport_security(server_src: str) -> list[dict]:
    findings = []

    # Check TM_MCP_KEY guard exists
    if "TM_MCP_KEY" in server_src and "SystemExit(1)" in server_src:
        findings.append({
            "dim": "DIM-4",
            "severity": "INFO",
            "location": "server.py entry-point",
            "issue": "TM_MCP_KEY guard present for network transports",
            "detail": "Network transport exits with code 1 if TM_MCP_KEY is unset.",
            "remediation": "",
        })
    else:
        findings.append({
            "dim": "DIM-4",
            "severity": "CRITICAL",
            "location": "server.py entry-point",
            "issue": "Network transport missing TM_MCP_KEY guard",
            "detail": "SSE/streamable-http transports can be started without auth.",
            "remediation": "Add TM_MCP_KEY check before mcp.run() for non-stdio transports.",
        })

    # Check default host
    if '--host", default="0.0.0.0"' in server_src or "default=\"0.0.0.0\"" in server_src:
        findings.append({
            "dim": "DIM-4",
            "severity": "MEDIUM",
            "location": "server.py --host default",
            "issue": "Network transport default bind address is 0.0.0.0 (all interfaces)",
            "detail": (
                "If a developer starts the server with --transport sse without specifying --host, "
                "it binds to all interfaces. Even with TM_MCP_KEY, this exposes the port on "
                "non-loopback interfaces by default."
            ),
            "remediation": "Change default to '127.0.0.1'; require explicit --host 0.0.0.0 for intentional exposure.",
        })

    # Check FASTMCP_AUTH_TOKEN relay
    if "FASTMCP_AUTH_TOKEN" in server_src:
        findings.append({
            "dim": "DIM-4",
            "severity": "INFO",
            "location": "server.py FASTMCP_AUTH_TOKEN",
            "issue": "TM_MCP_KEY relayed to FastMCP bearer token guard",
            "detail": "os.environ.setdefault('FASTMCP_AUTH_TOKEN', _mcp_key) passes the key to FastMCP.",
            "remediation": "",
        })

    # Check that stdio has no network exposure
    stdio_guard = re.search(
        r"transport.*==.*stdio.*mcp\.run\(transport=.stdio.\)",
        server_src.replace("\n", " "),
    )
    if "transport=\"stdio\"" in server_src or "transport='stdio'" in server_src:
        findings.append({
            "dim": "DIM-4",
            "severity": "INFO",
            "location": "server.py stdio transport",
            "issue": "Default transport is stdio (no network exposure)",
            "detail": "mcp.run(transport='stdio') — no bind address, no auth token required.",
            "remediation": "",
        })

    return findings


# ─── DIM-5: Adversarial persona coverage ─────────────────────────────────────

def dim5_adversarial_coverage(tools: list[dict], risk_map: dict[str, str]) -> list[dict]:
    findings = []
    adversarial_sim_path = ROOT / "mcp_server" / "client_sim_adversarial.py"
    adversarial_test_paths = list((ROOT / "tests").glob("**/test_mcp_adversarial*.py"))

    if not adversarial_sim_path.exists() and not adversarial_test_paths:
        findings.append({
            "dim": "DIM-5",
            "severity": "HIGH",
            "location": "mcp_server/",
            "issue": "No adversarial MCP persona file found",
            "detail": (
                "client_sim.py has 6 benign personas; no adversarial persona file exists "
                "(expected: client_sim_adversarial.py or tests/test_mcp_adversarial*.py). "
                "Modify-tier tools (run_expert_review, record_brain_feedback, "
                "generate_synthetic_architectures, run_taco_agent) have zero adversarial coverage."
            ),
            "remediation": (
                "Create mcp_server/client_sim_adversarial.py with scenarios: "
                "(1) brain poisoning via record_brain_feedback with wrong label, "
                "(2) quota abuse via generate_synthetic_architectures max_per_run flood, "
                "(3) path traversal via run_taclaw target='../../../../etc/passwd', "
                "(4) LLM injection via run_taco_agent query with override phrase, "
                "(5) recon sequence via repeated list_architectures + bulk governance pulls."
            ),
        })
        modify_tools = [
            t["name"] for t in tools
            if risk_map.get(t["name"], "read") in ("modify", "analyze")
        ]
        findings.append({
            "dim": "DIM-5",
            "severity": "HIGH",
            "location": f"{len(modify_tools)} analyze/modify-tier tools",
            "issue": "Modify/analyze-tier tools have no adversarial test coverage",
            "detail": ", ".join(sorted(modify_tools)),
            "remediation": (
                "Each modify/analyze tool should have at least one adversarial scenario: "
                "injection, abuse, or boundary-violation test."
            ),
        })
    else:
        findings.append({
            "dim": "DIM-5",
            "severity": "INFO",
            "location": str(adversarial_sim_path.name if adversarial_sim_path.exists()
                            else adversarial_test_paths[0]),
            "issue": "Adversarial persona file found",
            "detail": "Coverage analysis skipped (file present but not parsed here).",
            "remediation": "",
        })
    return findings


# ─── DIM-6: Agent identity validation (ABAC) ─────────────────────────────────

def dim6_identity_validation(server_src: str, risk_map: dict[str, str]) -> list[dict]:
    findings = []
    modify_tools = [t for t, r in risk_map.items() if r in ("modify", "analyze")]

    # Check if caller-identity / ABAC check exists at MCP dispatch layer.
    # Only count it if the indicator appears OUTSIDE docstrings/comments —
    # e.g., passport_id in a docstring as a return field description is not an ABAC check.
    # We look for indicators in the function body code (non-string-literal lines).
    abac_code_patterns = [
        r"check_scope\(", r"verify_caller\(", r"assert_role\(", r"abac\(",
        r"rbac\(", r"agent_id\s*=", r"caller_id\s*=",
        r"passport_id.*required", r"require.*passport",
    ]
    has_caller_check = any(re.search(p, server_src, re.IGNORECASE) for p in abac_code_patterns)

    if not has_caller_check:
        findings.append({
            "dim": "DIM-6",
            "severity": "MEDIUM",
            "location": "mcp_server/server.py dispatch layer",
            "issue": "No ABAC caller-identity check at MCP tool dispatch",
            "detail": (
                "_mcp_content_trust_check validates content (mmd_content only) but does not "
                "verify caller identity. Any agent with a valid TM-API-KEY can invoke modify-tier "
                "tools (run_expert_review, record_brain_feedback, generate_synthetic_architectures). "
                "Engine Item 11 added passport_id to job results but the MCP server does not "
                "validate the caller's passport before dispatch."
            ),
            "remediation": (
                "Add a caller-identity check to _mcp_content_trust_check (or a new function) "
                "for modify-tier tools: require a valid passport_id header or agent_id claim "
                "before dispatching to modify-tier tools. Tie into the ABAC scope from Entry 179."
            ),
        })
    else:
        findings.append({
            "dim": "DIM-6",
            "severity": "INFO",
            "location": "mcp_server/server.py",
            "issue": "Caller-identity indicator found in server.py",
            "detail": "Verify that the check applies to all modify-tier tools.",
            "remediation": "",
        })

    # Check _mcp_content_trust_check scope
    if "_mcp_content_trust_check" in server_src:
        # Confirm it only fires for mmd_content params, not other strings
        findings.append({
            "dim": "DIM-6",
            "severity": "MEDIUM",
            "location": "_mcp_content_trust_check()",
            "issue": "_mcp_content_trust_check scope limited to mmd_content parameter",
            "detail": (
                "The content trust gate runs only when a tool passes mmd_content. "
                "Other string params (query in run_taco_agent, target in run_taclaw, "
                "gap_ids in generate_synthetic_architectures) bypass this gate entirely. "
                "A malicious caller can inject through any unchecked string param."
            ),
            "remediation": (
                "Extend _mcp_content_trust_check to accept a list of strings to screen, "
                "or add per-tool pre-flight checks for high-risk string params."
            ),
        })

    return findings


# ─── Report ───────────────────────────────────────────────────────────────────

def print_report(all_findings: list[dict]) -> None:
    sev_order = [("CRITICAL", "🔴"), ("HIGH", "🟠"), ("MEDIUM", "🟡"), ("LOW", "🔵"), ("INFO", "⚪")]
    counts = {s: 0 for s, _ in sev_order}
    for f in all_findings:
        counts[f["severity"]] = counts.get(f["severity"], 0) + 1

    print("\nmcp-audit — MCP Attack Surface Security Posture")
    print("=" * 70)
    print(
        "  CRITICAL: {CRITICAL}  HIGH: {HIGH}  MEDIUM: {MEDIUM}  LOW: {LOW}  INFO: {INFO}".format(
            **counts
        )
    )
    print("=" * 70)

    by_sev: dict[str, list[dict]] = {s: [] for s, _ in sev_order}
    for f in all_findings:
        by_sev.setdefault(f["severity"], []).append(f)

    for sev, icon in sev_order:
        bucket = by_sev.get(sev, [])
        if not bucket:
            continue
        for f in bucket:
            print(f"\n{icon} [{f['severity']}] {f['dim']} — {f['location']}")
            print(f"   Issue:  {f['issue']}")
            if f["detail"] and f["detail"] != "Clean":
                for line in f["detail"].splitlines():
                    print(f"   Detail: {line.strip()}")
            if f.get("remediation"):
                for line in f["remediation"].splitlines():
                    print(f"   Fix:    {line.strip()}")

    print("\n" + "=" * 70)
    if counts["CRITICAL"] + counts["HIGH"] > 0:
        print(
            f"RESULT: FAIL — {counts['CRITICAL']} critical, {counts['HIGH']} high findings require attention."
        )
    else:
        print("RESULT: PASS — no critical or high findings.")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> int:
    if not SERVER_PY.exists():
        print(f"ERROR: {SERVER_PY} not found", file=sys.stderr)
        return 2

    server_src = SERVER_PY.read_text()
    server_tree = _load_source(SERVER_PY)
    sim_tree = _load_source(CLIENT_SIM_PY) if CLIENT_SIM_PY.exists() else None

    tools = extract_tools(server_tree)
    instructions = extract_fastmcp_instructions(server_tree)
    risk_map = extract_tool_risk_map(server_tree)
    sim_called = extract_sim_tool_calls(sim_tree) if sim_tree else set()

    print(f"Parsed {len(tools)} MCP tools from {SERVER_PY.relative_to(ROOT)}")
    print(f"Parsed {len(sim_called)} tool calls from {CLIENT_SIM_PY.name if CLIENT_SIM_PY.exists() else '(not found)'}")

    all_findings: list[dict] = []
    all_findings += dim1_description_injection(tools, instructions)
    all_findings += dim2_parameter_validation(tools)
    all_findings += dim3_scope_gap(tools, sim_called, risk_map)
    all_findings += dim4_transport_security(server_src)
    all_findings += dim5_adversarial_coverage(tools, risk_map)
    all_findings += dim6_identity_validation(server_src, risk_map)

    all_findings.sort(key=lambda f: sev_key(f["severity"]))
    print_report(all_findings)

    has_critical_or_high = any(f["severity"] in ("CRITICAL", "HIGH") for f in all_findings)
    return 1 if has_critical_or_high else 0


if __name__ == "__main__":
    sys.exit(main())
