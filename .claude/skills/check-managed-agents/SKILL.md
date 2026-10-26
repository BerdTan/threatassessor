---
name: check-managed-agents
description: Validate the TA managed agent fleet — capability declarations, fleet tool registry completeness, risk tier coherence, prover simulation, isolation pre-flight, DETECT-AGT-004 alignment, and optional live API posture check. Use after any change to chatbot/agents/managed/ or policies/agent_governance.yaml.
allowed-tools: Bash(python3:*)
---

# check-managed-agents — Managed Agent Fleet Posture Validation

Validates the managed agent fleet across 8 check dimensions (static, no LLM calls)
and optionally queries the live API for the CISO fleet posture endpoint.

## Coverage

| # | Check | What it verifies |
|---|-------|-----------------|
| 1 | Syntax | All managed agent files parse without errors |
| 2 | Imports | ManagedAgent, ManagedToolRegistry, get_registry, get_tool_registry all importable |
| 3 | Capability declarations | Every registered agent declares non-empty allowed_tools + allowed_endpoints |
| 4 | Tool registry completeness | Every tool in allowed_tools has a ToolRegistration in the fleet catalog |
| 5 | Risk tier coherence | Flags/tier fields are internally consistent (no write tool as read_only, etc.) |
| 6 | Prover simulation | No dead allowed_tools entries; no cross-agent permitted_agents violations |
| 7 | Isolation pre-flight | agent_governance.yaml exists and is parseable (confirm_isolation prerequisite) |
| 8 | DETECT alignment | DETECT-AGT-004 (tool_restriction_bypass) present in soc_detection_rules.yaml |
| 9 | Live API | GET /api/v1/agents/fleet-posture + /tools — posture label + catalog count (--live only) |

## Run

```bash
# Static checks only (~2s, no network)
python3 .claude/skills/check-managed-agents/scripts/check-managed-agents.py

# Static + live API posture check (API must be running)
python3 .claude/skills/check-managed-agents/scripts/check-managed-agents.py --live

# Against a non-default API URL
python3 .claude/skills/check-managed-agents/scripts/check-managed-agents.py --live --url http://localhost:8000
```

## Verdict

- **PASS** — all checks green; fleet posture is CLEAN
- **WARN** — one or more amber warnings (undeclared endpoints, risk tier notes)
- **FAIL** — one or more red failures (unregistered tools, cross-agent denials, import errors, broken isolation pre-flight)

## What to fix

| Symptom | Fix |
|---------|-----|
| `allowed_tools not declared` | Add `allowed_tools = [...]` class attribute to the agent |
| `tool not in fleet registry` | Pass `policy=ToolRegistration(...)` to `_add_tool()` |
| `permitted_agents violation` | Add the agent_id to `permitted_agents` in the ToolRegistration, or remove the tool from that agent's allowed_tools |
| `risk tier incoherent` | Align flag fields with risk_tier (e.g. write_side_effects=True → risk_tier="write") |
| `governance yaml missing` | Restore policies/agent_governance.yaml — confirm_isolation() will block all agent runs |
| `DETECT-AGT-004 missing` | Restore the rule in policies/soc_detection_rules.yaml |
