"""
MCP Live Simulation — SSE stream for the dashboard MCP tab.

GET /api/v1/mcp/simulate/{persona}?arch={arch_name}

Runs a persona's tool chain step by step against the real REST API,
emitting one SSE event per step so the dashboard can animate the flow.

Event types:
  persona_start   — {persona, arch, description, steps: [{tool, label}]}
  tool_start      — {step, tool, label, args}
  tool_result     — {step, tool, ok, summary, duration_ms}
  signal_update   — {mcp_access: {...}}           — after each tool call
  detect_fired    — {rule_id, name, severity}     — when a new rule fires
  sim_done        — {persona, total_steps, total_ms, detect_rules_fired: [...]}
  sim_error       — {message}

Personas: chatbot, code-agent, ciso, soc, copilot, chatgpt (benign)
          recon_attack, flood_attack, auth_probe (adversarial — trigger DETECT rules)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from typing import AsyncGenerator, Optional

import requests
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse

from chatbot.api.dependencies import verify_api_key

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["mcp-sim"])

# ---------------------------------------------------------------------------
# Persona definitions — each step is (tool_name, display_label, args_fn)
# args_fn receives arch_name and returns a dict (or None for no-arg tools)
# ---------------------------------------------------------------------------

def _personas(arch: str) -> dict:
    return {

        # ── Benign personas ───────────────────────────────────────────────

        "chatbot": {
            "description": "Conversational assistant — list → briefing → governance → MITRE",
            "steps": [
                ("list_architectures",    "List architectures",         lambda a: {}),
                ("get_threat_briefing",   "Get threat briefing",        lambda a: {"arch_name": a, "fmt": "json"}),
                ("get_governance_signals","Get governance signals",      lambda a: {"arch_name": a}),
                ("lookup_mitre_technique","Look up MITRE technique",     lambda a: {"technique_ids": "T1190,T1078"}),
            ],
        },

        "code-agent": {
            "description": "CI/CD gate — TATB scores + governance → pass/block decision",
            "steps": [
                ("get_tatb_scores",       "Get TATB scores",            lambda a: {"arch_name": a}),
                ("get_governance_signals","Check governance signals",    lambda a: {"arch_name": a}),
                ("get_detect_trends",     "Check DETECT trends",        lambda a: {"arch_name": a}),
            ],
        },

        "ciso": {
            "description": "Executive dashboard — CISO brief + corpus scorecard",
            "steps": [
                ("get_ciso_brief",        "Generate CISO brief",        lambda a: {"arch_name": a}),
                ("get_tatb_scores",       "Get corpus TATB scores",     lambda a: {}),
                ("get_detect_trends",     "Get DETECT trends",          lambda a: {"arch_name": a}),
            ],
        },

        "soc": {
            "description": "SOC analyst — DETECT trends → governance → MITRE triage",
            "steps": [
                ("get_detect_trends",     "Get DETECT trends",          lambda a: {"arch_name": a}),
                ("get_governance_signals","Pull governance signals",     lambda a: {"arch_name": a}),
                ("lookup_mitre_technique","Look up MITRE techniques",   lambda a: {"technique_ids": "T1059,T1055,T1562"}),
                ("get_mcp_access_signals","Check access signals",       lambda a: {}),
            ],
        },

        "copilot": {
            "description": "IDE inline assistant — MITRE lookup + quick briefing",
            "steps": [
                ("lookup_mitre_technique","MITRE inline lookup",        lambda a: {"technique_ids": "T1190,T1078,T1059"}),
                ("get_threat_briefing",   "Quick threat briefing",      lambda a: {"arch_name": a, "fmt": "json"}),
            ],
        },

        "chatgpt": {
            "description": "Custom GPT / OpenAI function-calling bridge",
            "steps": [
                ("list_architectures",    "List architectures",         lambda a: {}),
                ("get_threat_briefing",   "Retrieve briefing",          lambda a: {"arch_name": a, "fmt": "json"}),
                ("get_governance_signals","Get governance signals",      lambda a: {"arch_name": a}),
            ],
        },

        # ── Adversarial personas — deliberately trigger DETECT rules ─────

        "recon_attack": {
            "description": "⚠ Adversarial — enumerate all archs then bulk-pull signals (DETECT-020)",
            "steps": [
                ("list_architectures",    "Enumerate all architectures [recon step 1]",  lambda a: {}),
                ("get_governance_signals","Pull signals: arch_1 [recon step 2]",         lambda a: {"arch_name": a}),
                ("get_governance_signals","Pull signals: arch_2 [recon step 3]",         lambda a: {"arch_name": a}),
                ("get_governance_signals","Pull signals: arch_3 [recon step 4]",         lambda a: {"arch_name": a}),
                ("get_mcp_access_signals","Check own access footprint",                  lambda a: {}),
            ],
        },

        "flood_attack": {
            "description": "⚠ Adversarial — submit expert review jobs without polling (DETECT-021)",
            "steps": [
                ("run_expert_review",     "Submit job #1 [flood step 1]",   lambda a: {"arch_name": a, "critic_mode": "partial_parallel"}),
                ("run_expert_review",     "Submit job #2 [flood step 2]",   lambda a: {"arch_name": a, "critic_mode": "partial_parallel"}),
                ("run_expert_review",     "Submit job #3 [flood step 3]",   lambda a: {"arch_name": a, "critic_mode": "partial_parallel"}),
                ("get_mcp_access_signals","Check own access footprint",     lambda a: {}),
            ],
        },

        "auth_probe": {
            "description": "⚠ Adversarial — repeated bad-key calls to probe auth (DETECT-022)",
            "steps": [
                ("list_architectures",    "Probe with bad key #1 [auth step 1]",  lambda a: {"_bad_key": True}),
                ("list_architectures",    "Probe with bad key #2 [auth step 2]",  lambda a: {"_bad_key": True}),
                ("list_architectures",    "Probe with bad key #3 [auth step 3]",  lambda a: {"_bad_key": True}),
                ("list_architectures",    "Probe with bad key #4 [auth step 4]",  lambda a: {"_bad_key": True}),
                ("list_architectures",    "Probe with bad key #5 [auth step 5]",  lambda a: {"_bad_key": True}),
                ("get_mcp_access_signals","Check own access footprint",           lambda a: {}),
            ],
        },
    }


# ---------------------------------------------------------------------------
# REST caller — hits /api/v1/* directly (same process, loopback)
# ---------------------------------------------------------------------------

def _api_url() -> str:
    return os.environ.get("TM_API_BASE_URL", "http://localhost:8000")


def _call_tool(tool: str, args: dict, bad_key: bool = False) -> tuple[bool, dict, float]:
    """Call the REST API equivalent of an MCP tool. Returns (ok, summary_dict, ms)."""
    api_key = os.environ.get("API_KEY", os.environ.get("TM_API_KEY", ""))
    headers = {
        "TM-API-KEY": "bad-key-intentional" if bad_key else api_key,
        "Content-Type": "application/json",
    }
    base = _api_url()
    t0 = time.time()

    _TOOL_MAP = {
        "list_architectures":    ("GET",  "/api/v1/insights/all",          None),
        "get_threat_briefing":   ("GET",  "/api/v1/reports/{arch_name}/briefing", None),
        "get_governance_signals":("GET",  "/api/v1/insights",              {"archs": args.get("arch_name", "")}),
        "get_detect_trends":     ("GET",  "/api/v1/detect-trend/{arch_name}", None),
        "get_tatb_scores":       ("GET",  "/api/v1/tatb-corpus",           None),
        "get_ciso_brief":        ("POST", "/api/v1/reports/{arch_name}/generate-ciso-brief", {}),
        "lookup_mitre_technique":("GET",  "/api/v1/techniques",            {"technique_ids": args.get("technique_ids", "T1566")}),
        "run_expert_review":     ("POST", "/api/v1/jobs/expert-review",    {"arch_name": args.get("arch_name", ""), "critic_mode": args.get("critic_mode", "partial_parallel")}),
        "get_job_status":        ("GET",  "/api/v1/jobs/{job_id}/status",  None),
        "get_mcp_access_signals":("GET",  "/api/v1/mcp/access-signals",   None),
    }

    spec = _TOOL_MAP.get(tool)
    if not spec:
        return False, {"error": f"unknown tool: {tool}"}, 0.0

    method, path_tpl, body = spec
    path = path_tpl.format(
        arch_name=args.get("arch_name", ""),
        job_id=args.get("job_id", ""),
    )
    url = f"{base}{path}"

    try:
        if method == "GET":
            params = body  # body is query params for GET
            r = requests.get(url, headers=headers, params=params, timeout=15)
        else:
            r = requests.post(url, headers=headers, json=body or {}, timeout=15)
        ms = round((time.time() - t0) * 1000)
        ok = r.status_code < 400 or r.status_code == 404
        # Build a short summary of the result
        try:
            data = r.json()
        except Exception:
            data = {}
        summary = _summarise(tool, r.status_code, data)
        return ok, {"status_code": r.status_code, "summary": summary, "auth_failed": r.status_code == 401}, ms
    except Exception as exc:
        ms = round((time.time() - t0) * 1000)
        return False, {"error": str(exc), "auth_failed": False}, ms


def _summarise(tool: str, status: int, data: dict) -> str:
    """One-line human summary of a tool result for the timeline."""
    if status == 401:
        return "401 Unauthorized"
    if status == 404:
        return "404 Not Found"
    if status >= 500:
        return f"{status} Server Error"
    if tool == "list_architectures":
        n = len(data) if isinstance(data, list) else len(data.get("architectures", []))
        return f"{n} architectures"
    if tool == "get_threat_briefing":
        risk = data.get("risk_level") or data.get("overall_risk", "—")
        return f"risk: {risk}"
    if tool == "get_governance_signals":
        archs = data.get("architectures", [data] if data else [])
        lvl = archs[0].get("overall_risk_level", "—") if archs else "—"
        return f"risk level: {lvl}"
    if tool == "get_tatb_scores":
        n = len(data.get("architectures", []))
        return f"{n} architectures scored"
    if tool == "get_detect_trends":
        rules = data.get("rules") or data.get("trends") or {}
        fired = sum(1 for r in rules.values() if isinstance(r, dict) and r.get("fire_count", 0) > 0) if isinstance(rules, dict) else 0
        return f"{fired} rules with activity"
    if tool == "run_expert_review":
        return f"job_id: {data.get('job_id', '?')[:8]}…"
    if tool == "get_mcp_access_signals":
        mac = data.get("mcp_access", {})
        flags = [k for k in ("recon_sequence", "job_flood", "auth_failures") if mac.get(k)]
        return f"signals: {', '.join(flags) or 'clean'}"
    if tool == "lookup_mitre_technique":
        n = len(data.get("techniques", {}))
        return f"{n} technique(s)"
    if tool == "get_ciso_brief":
        return "brief generated" if data else "no data"
    return "ok"


# ---------------------------------------------------------------------------
# SSE generator
# ---------------------------------------------------------------------------

def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _sim_stream(persona: str, arch: str) -> AsyncGenerator[str, None]:
    personas = _personas(arch)
    if persona not in personas:
        yield _sse("sim_error", {"message": f"Unknown persona '{persona}'"})
        return

    cfg = personas[persona]
    steps = cfg["steps"]
    is_adversarial = persona in ("recon_attack", "flood_attack", "auth_probe")

    # Record baseline DETECT rules before sim starts
    from mcp_server.access_logger import get_access_logger
    access_log = get_access_logger()
    baseline_signals = access_log.get_signals().get("mcp_access", {})
    prev_flags = {k: baseline_signals.get(k, False)
                  for k in ("recon_sequence", "job_flood", "auth_failures")}

    _RULE_MAP = {
        "recon_sequence": ("DETECT-020", "MCP Recon Sequence",    "Medium"),
        "job_flood":      ("DETECT-021", "MCP Job Flooding",      "High"),
        "auth_failures":  ("DETECT-022", "MCP Auth Probing",      "High"),
    }

    yield _sse("persona_start", {
        "persona":     persona,
        "arch":        arch,
        "description": cfg["description"],
        "adversarial": is_adversarial,
        "steps": [{"tool": s[0], "label": s[1]} for s in steps],
    })
    await asyncio.sleep(0.05)

    sim_start = time.time()
    total_steps = len(steps)

    for i, (tool, label, args_fn) in enumerate(steps):
        raw_args = args_fn(arch)
        bad_key = raw_args.pop("_bad_key", False)
        display_args = {k: v for k, v in raw_args.items() if v}

        yield _sse("tool_start", {
            "step":  i,
            "total": total_steps,
            "tool":  tool,
            "label": label,
            "args":  display_args,
        })
        await asyncio.sleep(0.1)

        # Execute tool call
        ok, result, ms = await asyncio.to_thread(_call_tool, tool, raw_args, bad_key)

        # Record in access logger (adversarial auth probe logs the failure)
        if bad_key or result.get("auth_failed"):
            access_log.record_tool_call(tool, arch_name=arch, success=False, auth_failed=True)
        else:
            access_log.record_tool_call(tool, arch_name=arch, success=ok)

        yield _sse("tool_result", {
            "step":        i,
            "tool":        tool,
            "ok":          ok,
            "status_code": result.get("status_code"),
            "summary":     result.get("summary", ""),
            "auth_failed": result.get("auth_failed", False),
            "duration_ms": ms,
        })
        await asyncio.sleep(0.05)

        # Check for newly fired DETECT rules
        new_signals = access_log.get_signals().get("mcp_access", {})
        yield _sse("signal_update", {"mcp_access": new_signals})

        for flag, (rule_id, rule_name, severity) in _RULE_MAP.items():
            if new_signals.get(flag) and not prev_flags.get(flag):
                yield _sse("detect_fired", {
                    "rule_id":  rule_id,
                    "name":     rule_name,
                    "severity": severity,
                    "trigger":  flag,
                })
                prev_flags[flag] = True
                await asyncio.sleep(0.05)

        # Pacing — give UI time to animate
        await asyncio.sleep(0.6 if is_adversarial else 0.4)

    total_ms = round((time.time() - sim_start) * 1000)
    final_signals = access_log.get_signals().get("mcp_access", {})
    fired_rules = [_RULE_MAP[k][0] for k in ("recon_sequence", "job_flood", "auth_failures")
                   if final_signals.get(k)]

    yield _sse("sim_done", {
        "persona":             persona,
        "total_steps":         total_steps,
        "total_ms":            total_ms,
        "detect_rules_fired":  fired_rules,
        "final_signals":       final_signals,
    })


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------

@router.get("/mcp/simulate/{persona}", dependencies=[Depends(verify_api_key)])
async def simulate_persona(
    persona: str,
    arch: str = Query(default="web_app", description="Architecture name to use in tool calls"),
):
    """SSE stream simulating an MCP client persona's tool chain.

    Emits events: persona_start, tool_start, tool_result, signal_update,
    detect_fired, sim_done, sim_error.

    Personas: chatbot, code-agent, ciso, soc, copilot, chatgpt (benign)
              recon_attack, flood_attack, auth_probe (adversarial)
    """
    return StreamingResponse(
        _sim_stream(persona, arch),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/mcp/personas", dependencies=[Depends(verify_api_key)])
async def list_personas():
    """List available simulation personas with descriptions."""
    personas = _personas("_")
    return {
        "personas": [
            {
                "id":          pid,
                "description": cfg["description"],
                "steps":       len(cfg["steps"]),
                "adversarial": pid in ("recon_attack", "flood_attack", "auth_probe"),
            }
            for pid, cfg in personas.items()
        ]
    }
