#!/usr/bin/env python3
"""
ThreatAssessor MCP Client Simulator

Demonstrates how different client personas connect to and use the ThreatAssessor
MCP server. Each persona reflects a real integration pattern so teams can copy
the relevant section directly into their own service.

Personas
--------
  chatbot      — conversational assistant (chains tools, natural language output)
  code-agent   — CI/CD or code review agent (structured JSON, pipeline gates)
  ciso         — executive dashboard (brief + investment tiers, no raw JSON)
  soc          — SOC analyst (DETECT trends + governance signals + MITRE lookup)
  copilot      — IDE/Copilot style (quick inline lookup, minimal roundtrips)

Usage
-----
  # Run all personas against a live API
  python3 mcp_server/client_sim.py --all

  # Run one persona
  python3 mcp_server/client_sim.py --persona chatbot

  # Dry-run (list tools only, no real API calls needed)
  python3 mcp_server/client_sim.py --dry-run

  # Point at a non-default API
  python3 mcp_server/client_sim.py --all --api-url http://my-server:8000 --api-key secret

Environment variables (override CLI flags):
  TM_API_BASE_URL   REST API base URL  (default: http://localhost:8000)
  TM_API_KEY        REST API key
"""

import argparse
import asyncio
import json
import os
import sys
import textwrap
import time
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

REPO_ROOT = Path(__file__).resolve().parent.parent

# ── Colour helpers ────────────────────────────────────────────────────────────

GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"
YELLOW = lambda s: f"\033[33;1m{s}\033[0m"
BLUE   = lambda s: f"\033[34;1m{s}\033[0m"

# ── Server bootstrap ──────────────────────────────────────────────────────────

def _server_params(api_url: str, api_key: str) -> StdioServerParameters:
    """Build StdioServerParameters pointing at this repo's MCP server."""
    python = str(REPO_ROOT / ".venv" / "bin" / "python3")
    if not Path(python).exists():
        python = sys.executable  # fallback to current interpreter
    return StdioServerParameters(
        command=python,
        args=["-m", "mcp_server.server"],
        cwd=str(REPO_ROOT),
        env={
            **os.environ,
            "TM_API_BASE_URL": api_url,
            "TM_API_KEY": api_key,
        },
    )


async def _connect(api_url: str, api_key: str):
    """Context manager: yield an initialised ClientSession."""
    params = _server_params(api_url, api_key)
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


# ── Tool call helper ──────────────────────────────────────────────────────────

async def resolve_arch(session: ClientSession, arch_name: str) -> str:
    """Return arch_name if it exists in the corpus, else fall back to first available."""
    data = await call(session, "list_architectures")
    archs = data if isinstance(data, list) else data.get("architectures", [])
    names = [a.get("name") or a.get("arch_name") or str(a) for a in archs] if archs else []
    if arch_name in names:
        return arch_name
    if names:
        _warn(f"'{arch_name}' not found — using first available: {names[0]}")
        return names[0]
    return arch_name


async def call(session: ClientSession, tool: str, **kwargs) -> dict:
    """Call a tool, parse JSON result, return as dict."""
    result = await session.call_tool(tool, arguments=kwargs or None)
    text = result.content[0].text if result.content else "{}"
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}


def _truncate(text: str, width: int = 120) -> str:
    text = str(text)
    return text[:width] + "…" if len(text) > width else text


def _section(title: str, persona: str, icon: str = "") -> None:
    pad = 60 - len(title)
    print(f"\n{BOLD(BLUE(f'{icon}  {title}'))}  {DIM('─' * max(0, pad))}")


def _step(n: int, label: str) -> None:
    print(f"\n  {CYAN(f'[{n}]')} {BOLD(label)}")


def _result(key: str, value) -> None:
    v = _truncate(str(value))
    print(f"      {DIM(key + ':')}  {v}")


def _ok(msg: str) -> None:
    print(f"      {GREEN('✓')}  {msg}")


def _warn(msg: str) -> None:
    print(f"      {AMBER('!')}  {msg}")


def _err(msg: str) -> None:
    print(f"      {RED('✗')}  {msg}")


def _code_block(label: str, code: str) -> None:
    print(f"\n  {DIM('# ' + label)}")
    for line in textwrap.dedent(code).strip().splitlines():
        print(f"  {DIM(line)}")


# ── Persona: Dry-run ─────────────────────────────────────────────────────────

async def persona_dry_run(api_url: str, api_key: str) -> None:
    """Connect and list tools only — no real API calls required."""
    _section("Dry-run — tool discovery", "dry-run", "🔍")
    print(f"  {DIM('Connects to server, lists tools, no tool calls made.')}\n")

    async with stdio_client(_server_params(api_url, api_key)) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            print(f"  {GREEN('✓')}  Server: {BOLD(init.serverInfo.name)}  "
                  f"v{init.serverInfo.version}")

            result = await session.list_tools()
            print(f"  {GREEN('✓')}  {len(result.tools)} tools registered:\n")
            for t in result.tools:
                desc = (t.description or "").splitlines()[0][:80]
                print(f"    {BOLD(t.name)}")
                print(f"    {DIM(desc)}")
                if t.inputSchema and t.inputSchema.get("properties"):
                    props = ", ".join(t.inputSchema["properties"].keys())
                    print(f"    {DIM('args: ' + props)}")
                print()

    _code_block("How to reproduce (Python)", """
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client
        import asyncio

        params = StdioServerParameters(
            command="python", args=["-m", "mcp_server.server"],
            env={"TM_API_BASE_URL": "http://localhost:8000", "TM_API_KEY": "..."},
        )

        async def main():
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    print([t.name for t in tools.tools])

        asyncio.run(main())
    """)


# ── Persona: Chatbot ──────────────────────────────────────────────────────────

async def persona_chatbot(session: ClientSession, arch_name: str) -> None:
    """
    Conversational assistant pattern.

    Chains: list → briefing → governance signals → MITRE lookup.
    Simulates what an LLM assistant does when a user asks
    "Tell me about the security posture of my web_app architecture."
    """
    _section("Chatbot / Conversational Assistant", "chatbot", "💬")
    print(f"  {DIM('Pattern: list → briefing → governance → MITRE drill-down')}")
    print(f"  {DIM('Use case: LLM assistant answering security posture questions')}\n")

    _step(1, "Discover what architectures are available")
    data = await call(session, "list_architectures")
    archs = data if isinstance(data, list) else data.get("architectures", [])
    names = [a.get("name") or a.get("arch_name") or str(a) for a in archs] if archs else []
    if names:
        _ok(f"{len(names)} architectures found: {', '.join(names[:5])}")
        if arch_name not in names:
            arch_name = names[0]
            _warn(f"Using first available: {arch_name}")
    else:
        _warn("No architectures found — using provided name anyway")

    _step(2, f"Get threat briefing for '{arch_name}'")
    briefing = await call(session, "get_threat_briefing", arch_name=arch_name, fmt="md")
    if "error" in briefing:
        _err(briefing["error"])
    elif "raw" in briefing:
        _ok("Briefing retrieved (markdown)")
        lines = briefing["raw"].splitlines()
        _result("preview", _truncate(lines[0] if lines else "", 80))
    else:
        _ok("Briefing retrieved")
        _result("risk_level",   briefing.get("risk_level") or briefing.get("overall_risk"))
        _result("top_threat",   (briefing.get("top_threats") or [{}])[0])
        _result("confidence",   briefing.get("confidence"))

    _step(3, "Get governance signals (AIVSS)")
    gov = await call(session, "get_governance_signals", arch_name=arch_name)
    if "error" in gov:
        _err(gov["error"])
    else:
        _ok("Governance signals retrieved")
        arch_data = (gov.get("architectures") or [gov])[0] if gov else {}
        aivss = arch_data.get("aivss", {}).get("overall", {}) or arch_data.get("aivss_overall") or {}
        _result("aivss_composite", aivss.get("composite") if isinstance(aivss, dict) else aivss)
        _result("risk_level",      arch_data.get("overall_risk_level"))

    _step(4, "Drill into top MITRE technique")
    techniques_raw = briefing.get("mitre_techniques") or briefing.get("top_techniques") or []
    tid = None
    if techniques_raw and isinstance(techniques_raw[0], dict):
        tid = techniques_raw[0].get("id") or techniques_raw[0].get("technique_id")
    elif techniques_raw and isinstance(techniques_raw[0], str):
        tid = techniques_raw[0]
    if tid:
        mitre = await call(session, "lookup_mitre_technique", technique_ids=tid)
        _ok(f"MITRE lookup for {tid}")
        techs = mitre.get("techniques", {})
        if isinstance(techs, dict) and tid in techs:
            _result("name",    techs[tid].get("name"))
            _result("tactics", techs[tid].get("tactics"))
    else:
        _warn("No MITRE technique IDs in briefing — skipping lookup")

    _code_block("Integration snippet (Python + any LLM)", """
        # In your LLM tool-use loop:
        tools_response = await session.list_tools()
        # Pass tools_response.tools as tool_definitions to your LLM
        # When LLM calls a tool:
        result = await session.call_tool(tool_name, arguments=tool_args)
        # Feed result.content[0].text back to LLM as tool_result
    """)


# ── Persona: Code Agent / CI-CD ───────────────────────────────────────────────

async def persona_code_agent(session: ClientSession, arch_name: str) -> None:
    """
    CI/CD pipeline gate pattern.

    Chains: analyze → TATB scores → governance signals → gate decision.
    Simulates a GitHub Actions step that blocks a PR if AIVSS score is HIGH+
    or TATB drops below threshold.
    """
    _section("Code Agent / CI-CD Gate", "code-agent", "⚙️")
    print(f"  {DIM('Pattern: analyze → TATB → governance → gate (pass/block)')}")
    print(f"  {DIM('Use case: GitHub Actions / GitLab CI threat gate on architecture changes')}\n")

    TATB_THRESHOLD   = 60   # block PR if any TATB dimension < this
    AIVSS_BLOCK_SEV  = {"CRITICAL", "HIGH"}

    _step(1, "Get TATB scores for corpus")
    tatb = await call(session, "get_tatb_scores", arch_name=arch_name)
    archs = tatb.get("architectures", [])
    target = next((a for a in archs if a.get("name") == arch_name), None)
    if target:
        scores = {
            "threat_relevant":   target.get("threat_relevant", 0),
            "ttp_accurate":      target.get("ttp_accurate", 0),
            "risk_defensible":   target.get("risk_defensible", 0),
            "plan_actionable":   target.get("plan_actionable", 0),
        }
        _ok(f"TATB scores: {scores}")
        low = {k: v for k, v in scores.items() if v < TATB_THRESHOLD}
        if low:
            _warn(f"Below threshold ({TATB_THRESHOLD}): {list(low.keys())}")
        else:
            _ok(f"All dimensions ≥ {TATB_THRESHOLD}")
    else:
        _warn(f"'{arch_name}' not in TATB corpus — treating as unscored")
        scores = {}

    _step(2, "Check governance signals")
    gov = await call(session, "get_governance_signals", arch_name=arch_name)
    arch_data = (gov.get("architectures") or [gov])[0] if gov else {}
    severity = arch_data.get("aivss_severity") or arch_data.get("overall_risk_level", "UNKNOWN")
    _result("severity", severity)

    _step(3, "Gate decision")
    blocked = (
        bool({str(severity).upper()} & AIVSS_BLOCK_SEV)
        or bool(scores and any(v < TATB_THRESHOLD for v in scores.values()))
    )
    if blocked:
        _err(f"GATE: BLOCK — severity={severity}, low_tatb={list({k for k,v in scores.items() if v < TATB_THRESHOLD})}")
        print(f"\n  {RED('→ CI step should exit 1 to block the PR')}")
    else:
        _ok(f"GATE: PASS — severity={severity}, all TATB ≥ {TATB_THRESHOLD}")
        print(f"\n  {GREEN('→ CI step exits 0, PR can merge')}")

    _code_block("GitHub Actions step (YAML)", """
        - name: ThreatAssessor gate
          run: |
            python3 mcp_server/client_sim.py --persona code-agent \\
              --arch ${{ github.event.repository.name }} \\
              --api-url ${{ secrets.TA_API_URL }} \\
              --api-key ${{ secrets.TA_API_KEY }}
          # exits 1 if gate blocks, 0 if pass
    """)


# ── Persona: CISO Dashboard ───────────────────────────────────────────────────

async def persona_ciso(session: ClientSession, arch_name: str) -> None:
    """
    CISO executive dashboard pattern.

    Chains: list → CISO brief → TATB corpus (investment tier table).
    No raw JSON shown — output is always formatted for a non-technical reader.
    """
    _section("CISO Executive Dashboard", "ciso", "📊")
    print(f"  {DIM('Pattern: list → ciso_brief → tatb corpus summary')}")
    print(f"  {DIM('Use case: Weekly security posture email / Slack digest / dashboard widget')}\n")

    arch_name = await resolve_arch(session, arch_name)

    _step(1, "Get CISO brief")
    brief = await call(session, "get_ciso_brief", arch_name=arch_name)
    if "error" in brief:
        _err(brief["error"])
    else:
        _ok("CISO brief generated")
        _result("executive_summary", brief.get("executive_summary", "")[:120])
        tiers = brief.get("investment_tiers") or {}
        if tiers:
            for tier, items in list(tiers.items())[:3]:
                _result(f"tier:{tier}", f"{len(items) if isinstance(items, list) else items} items")

    _step(2, "Corpus-wide TATB scorecard")
    tatb = await call(session, "get_tatb_scores")
    archs = tatb.get("architectures", [])
    if archs:
        avg = lambda k: sum((a.get(k) or 0) for a in archs) / len(archs)
        _ok(f"{len(archs)} architectures scored")
        _result("avg threat_relevant",  f"{avg('threat'):.0f}")
        _result("avg ttp_accurate",     f"{avg('ttp'):.0f}")
        _result("avg risk_defensible",  f"{avg('risk'):.0f}")
        _result("avg plan_actionable",  f"{avg('plan'):.0f}")
    else:
        _warn("No TATB corpus data returned")

    _code_block("Slack digest integration (Python)", """
        brief   = await session.call_tool("get_ciso_brief",   {"arch_name": arch})
        tatb    = await session.call_tool("get_tatb_scores",  {})
        payload = format_slack_digest(brief, tatb)   # your formatter
        slack_client.chat_postMessage(channel="#ciso", **payload)
    """)


# ── Persona: SOC Analyst ──────────────────────────────────────────────────────

async def persona_soc(session: ClientSession, arch_name: str) -> None:
    """
    SOC analyst workflow pattern.

    Chains: detect_trends → governance_signals → MITRE lookup for fired rules.
    Simulates a Tier-1 analyst triaging new DETECT alerts.
    """
    _section("SOC Analyst", "soc", "🛡️")
    print(f"  {DIM('Pattern: detect_trends → governance → MITRE drill-down on fired rules')}")
    print(f"  {DIM('Use case: SIEM enrichment, Tier-1 triage, incident response kick-off')}\n")

    arch_name = await resolve_arch(session, arch_name)

    _step(1, "Check DETECT rule firing trends")
    trends = await call(session, "get_detect_trends", arch_name=arch_name)
    rules = trends.get("rules") or trends.get("trends") or {}
    fired = {rid: r for rid, r in rules.items()
             if r.get("trend") not in ("never", None) and r.get("fire_count", 0) > 0} \
            if isinstance(rules, dict) else {}
    if fired:
        _ok(f"{len(fired)} rule(s) with activity:")
        for rid, r in list(fired.items())[:5]:
            _result(rid, f"trend={r.get('trend')}  fires={r.get('fire_count')}  sev={r.get('severity')}")
    else:
        _warn("No fired DETECT rules found for this architecture")

    _step(2, "Pull full governance signals for context")
    gov = await call(session, "get_governance_signals", arch_name=arch_name)
    arch_data = (gov.get("architectures") or [gov])[0] if gov else {}
    for sig in ["injection", "evasion", "pii_leakage", "manipulation", "sovereignty"]:
        v = arch_data.get(sig)
        if v not in (None, {}, False, 0):
            _result(sig, v)

    _step(3, "MITRE lookup for techniques tied to fired rules")
    technique_ids = []
    for r in (list(fired.values()) if fired else []):
        technique_ids.extend(r.get("mitre_techniques", []))
    technique_ids = list(dict.fromkeys(technique_ids))[:5]  # dedup, cap at 5

    if technique_ids:
        mitre = await call(session, "lookup_mitre_technique",
                           technique_ids=",".join(technique_ids))
        techs = mitre.get("techniques", {})
        mits  = mitre.get("mitigations", {})
        _ok(f"MITRE data for {len(techs)} technique(s):")
        for tid, t in list(techs.items())[:3]:
            _result(tid, t.get("name"))
        if mits:
            _result("mitigations", f"{sum(len(v) for v in mits.values() if isinstance(v, list))} total")
    else:
        _warn("No MITRE technique IDs on fired rules — try after expert review runs")

    _code_block("SIEM/SOAR enrichment (Python)", """
        async def enrich_alert(alert_arch: str) -> dict:
            trends = await session.call_tool("get_detect_trends", {"arch_name": alert_arch})
            gov    = await session.call_tool("get_governance_signals", {"arch_name": alert_arch})
            # Parse and push to your SIEM (Splunk/Sentinel/Chronicle)
            return build_enrichment_record(trends, gov)
    """)


# ── Persona: Copilot / IDE ────────────────────────────────────────────────────

async def persona_copilot(session: ClientSession, arch_name: str) -> None:
    """
    IDE Copilot / inline assistant pattern.

    Single-shot: lookup_mitre_technique for IDs the developer just touched
    in their code. Minimal roundtrips, immediate inline answer.
    """
    _section("IDE Copilot / Inline Assistant", "copilot", "✏️")
    print(f"  {DIM('Pattern: single-shot MITRE lookup + briefing summary')}")
    print(f"  {DIM('Use case: VS Code / JetBrains / GitHub Copilot extension')}\n")

    # Simulate developer hovering over a known ATT&CK ID in code comment
    SAMPLE_IDS = "T1190,T1078,T1059"

    _step(1, f"Inline MITRE lookup ({SAMPLE_IDS})")
    mitre = await call(session, "lookup_mitre_technique", technique_ids=SAMPLE_IDS)
    techs = mitre.get("techniques", {})
    mits  = mitre.get("mitigations", {})
    _ok(f"{len(techs)} techniques, {sum(len(v) for v in mits.values() if isinstance(v, list))} mitigations")
    for tid, t in techs.items():
        _result(tid, f"{t.get('name')}  |  {', '.join(t.get('tactics', [])[:3])}")

    _step(2, "Quick threat briefing (summary mode)")
    resolved = await resolve_arch(session, arch_name)
    brief = await call(session, "get_threat_briefing", arch_name=resolved, fmt="md")
    if "error" in brief:
        _err(brief["error"])
    elif "raw" in brief:
        _ok("Briefing retrieved — showing first line for inline display")
        lines = brief["raw"].splitlines()
        _result("preview", _truncate(lines[0] if lines else "", 80))
    else:
        _ok("Briefing retrieved — showing top 3 fields for inline display")
        for k in ["risk_level", "overall_risk", "confidence", "top_threats"]:
            if brief.get(k):
                _result(k, brief[k])
                break

    _code_block("VS Code extension (TypeScript + MCP SDK)", """
        import { Client } from "@modelcontextprotocol/sdk/client/index.js";
        import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

        const transport = new StdioClientTransport({
          command: "python",
          args: ["-m", "mcp_server.server"],
          env: { TM_API_BASE_URL: "http://localhost:8000", TM_API_KEY: "..." },
        });
        const client = new Client({ name: "copilot-ext", version: "1.0" });
        await client.connect(transport);

        const result = await client.callTool({
          name: "lookup_mitre_technique",
          arguments: { technique_ids: "T1190,T1078" },
        });
        vscode.window.showInformationMessage(result.content[0].text);
    """)


# ── Persona: ChatGPT Plugin / Custom GPT ─────────────────────────────────────

async def persona_chatgpt(session: ClientSession, arch_name: str) -> None:
    """
    ChatGPT Plugin / Custom GPT action pattern.

    Demonstrates the same tool calls a GPT Action (REST-over-HTTP) or
    OpenAI function-calling loop would issue when bridged via an MCP-to-REST
    adapter. The tools map 1:1 to the OpenAPI spec.
    """
    _section("ChatGPT Plugin / Custom GPT Action", "chatgpt", "🤖")
    print(f"  {DIM('Pattern: list → analyze (submit MMD) → briefing')}")
    print(f"  {DIM('Use case: Custom GPT with ThreatAssessor as a tool, or OpenAI function-calling')}\n")

    _step(1, "Discover available architectures (maps to GET /api/v1/insights/all)")
    data = await call(session, "list_architectures")
    archs = data if isinstance(data, list) else data.get("architectures", [])
    names = [a.get("name") or a.get("arch_name") or str(a) for a in archs] if archs else []
    _ok(f"{len(names)} architectures available")
    arch_name = await resolve_arch(session, arch_name)

    _step(2, "Retrieve threat briefing (maps to GET /api/v1/reports/{arch}/briefing)")
    brief = await call(session, "get_threat_briefing", arch_name=arch_name, fmt="md")
    if "error" in brief:
        _err(brief.get("error"))
    elif "raw" in brief:
        _ok("Briefing retrieved — GPT would format this as natural language answer")
        lines = brief["raw"].splitlines()
        _result("preview", _truncate(lines[0] if lines else "", 80))
    else:
        _ok("Briefing retrieved")
        _result("confidence", brief.get("confidence"))
        _result("risk_level", brief.get("risk_level") or brief.get("overall_risk"))

    _step(3, "Get AIVSS score (maps to GET /api/v1/insights?archs={arch})")
    gov = await call(session, "get_governance_signals", arch_name=arch_name)
    arch_data = (gov.get("architectures") or [gov])[0] if gov else {}
    _result("risk_level",  arch_data.get("overall_risk_level"))

    _code_block("OpenAI function-calling bridge (Python)", """
        # In your OpenAI tool-use loop, map MCP tools → OpenAI function defs:
        mcp_tools = await session.list_tools()
        openai_functions = [
            {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            }
            for t in mcp_tools.tools
        ]
        # When OpenAI calls a function:
        mcp_result = await session.call_tool(
            fn_call.name,
            arguments=json.loads(fn_call.arguments),
        )
    """)


# ── Runner ────────────────────────────────────────────────────────────────────

PERSONAS = {
    "chatbot":    persona_chatbot,
    "code-agent": persona_code_agent,
    "ciso":       persona_ciso,
    "soc":        persona_soc,
    "copilot":    persona_copilot,
    "chatgpt":    persona_chatgpt,
}


async def run_persona(name: str, api_url: str, api_key: str, arch_name: str) -> None:
    fn = PERSONAS[name]
    t0 = time.time()
    try:
        async with stdio_client(_server_params(api_url, api_key)) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                await fn(session, arch_name)
    except Exception as e:
        print(f"\n  {RED('ERROR')} in persona '{name}': {e}")
        import traceback; traceback.print_exc()
    elapsed = time.time() - t0
    print(f"\n  {DIM(f'completed in {elapsed:.1f}s')}")


async def run_dry(api_url: str, api_key: str) -> None:
    t0 = time.time()
    try:
        await persona_dry_run(api_url, api_key)
    except Exception as e:
        print(f"\n  {RED('ERROR')} in dry-run: {e}")
        import traceback; traceback.print_exc()
    print(f"\n  {DIM(f'completed in {time.time() - t0:.1f}s')}")


async def main_async(args: argparse.Namespace) -> int:
    api_url  = args.api_url
    api_key  = args.api_key
    arch     = args.arch

    print(f"\n{BOLD('ThreatAssessor MCP Client Simulator')}")
    print(DIM(f"  api:  {api_url}"))
    print(DIM(f"  arch: {arch}"))

    if args.dry_run:
        await run_dry(api_url, api_key)
        return 0

    targets = list(PERSONAS.keys()) if args.all else [args.persona]
    for name in targets:
        await run_persona(name, api_url, api_key, arch)

    print(f"\n{'═' * 60}")
    print(BOLD(f"  Done — {len(targets)} persona(s) exercised"))
    print(DIM("  All integration snippets above are copy-paste ready.\n"))
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="ThreatAssessor MCP client simulator — one persona per integration pattern",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        personas:
          chatbot      conversational assistant (chains tools, LLM integration)
          code-agent   CI/CD gate (TATB + AIVSS threshold check, exit code)
          ciso         executive dashboard (CISO brief + corpus scorecard)
          soc          SOC analyst (DETECT trends + MITRE triage)
          copilot      IDE inline assistant (quick lookup, minimal roundtrips)
          chatgpt      ChatGPT plugin / Custom GPT / OpenAI function-calling
        """),
    )
    p.add_argument("--persona",  default="chatbot", choices=list(PERSONAS.keys()),
                   help="which persona to run (default: chatbot)")
    p.add_argument("--all",      action="store_true", help="run all personas in sequence")
    p.add_argument("--dry-run",  action="store_true", dest="dry_run",
                   help="connect and list tools only — no API calls needed")
    p.add_argument("--arch",     default="web_app",
                   help="architecture name to use (default: web_app)")
    p.add_argument("--api-url",  dest="api_url",
                   default=os.environ.get("TM_API_BASE_URL", "http://localhost:8000"))
    p.add_argument("--api-key",  dest="api_key",
                   default=os.environ.get("TM_API_KEY", os.environ.get("API_KEY", "")))

    args = p.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    sys.exit(main())
