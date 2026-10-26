#!/usr/bin/env python3
"""
check-managed-agents — TA managed agent fleet posture validation.

Usage:
    python3 check-managed-agents.py               # static checks only (~2s, no network)
    python3 check-managed-agents.py --live        # static + live API posture check
    python3 check-managed-agents.py --live --url http://localhost:8000
"""

import argparse
import ast
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO_ROOT))

GREEN  = lambda s: f"\033[32m{s}\033[0m"
AMBER  = lambda s: f"\033[33m{s}\033[0m"
RED    = lambda s: f"\033[31m{s}\033[0m"
DIM    = lambda s: f"\033[2m{s}\033[0m"
BOLD   = lambda s: f"\033[1m{s}\033[0m"
CYAN   = lambda s: f"\033[36m{s}\033[0m"
YELLOW = lambda s: f"\033[93m{s}\033[0m"

passed = failed = warned = 0


def ok(label: str, detail: str = "") -> None:
    global passed
    passed += 1
    print(f"  {GREEN('✓')}  {label}" + (f"  {DIM(detail)}" if detail else ""))


def fail(label: str, detail: str = "") -> None:
    global failed
    failed += 1
    print(f"  {RED('✗')}  {label}" + (f"\n      {RED(detail)}" if detail else ""))


def warn(label: str, detail: str = "") -> None:
    global warned
    warned += 1
    print(f"  {AMBER('!')}  {label}" + (f"  {DIM(detail)}" if detail else ""))


def skip(label: str, reason: str = "") -> None:
    print(f"  {DIM('-')}  {label}" + (f"  {DIM('— ' + reason)}" if reason else ""))


# ── Managed agent files ───────────────────────────────────────────────────────

AGENT_DIR = REPO_ROOT / "chatbot" / "agents" / "managed"

AGENT_FILES = [
    AGENT_DIR / "__init__.py",
    AGENT_DIR / "base.py",
    AGENT_DIR / "registry.py",
    AGENT_DIR / "tool_registry.py",
    AGENT_DIR / "taclaw_investigator.py",
]

GOVERNANCE_YAML = REPO_ROOT / "policies" / "agent_governance.yaml"
DETECT_RULES    = REPO_ROOT / "policies" / "soc_detection_rules.yaml"

EXPECTED_AGENTS = ["taclaw_investigator"]
RISK_TIERS      = {"read_only", "write", "credential_use", "external_network"}

# ── Section 1: Syntax ─────────────────────────────────────────────────────────

def check_syntax() -> None:
    print(f"\n{BOLD(CYAN('1. Syntax'))} — {len(AGENT_FILES)} files\n")
    for f in AGENT_FILES:
        if not f.exists():
            fail(f.name, "file not found")
            continue
        try:
            ast.parse(f.read_text())
            ok(f.name)
        except SyntaxError as exc:
            fail(f.name, str(exc))


# ── Section 2: Imports ────────────────────────────────────────────────────────

def check_imports() -> None:
    print(f"\n{BOLD(CYAN('2. Imports'))}\n")
    checks = [
        ("ManagedAgent",        "chatbot.agents.managed.base",         "ManagedAgent"),
        ("ManagedToolRegistry", "chatbot.agents.managed.tool_registry", "ManagedToolRegistry"),
        ("get_registry",        "chatbot.agents.managed.registry",      "get_registry"),
        ("get_tool_registry",   "chatbot.agents.managed.tool_registry", "get_tool_registry"),
        ("ToolRegistration",    "chatbot.agents.managed.tool_registry", "ToolRegistration"),
        ("RunCredentials",      "chatbot.agents.managed.base",          "RunCredentials"),
    ]
    for label, module, symbol in checks:
        try:
            mod = __import__(module, fromlist=[symbol])
            getattr(mod, symbol)
            ok(label, f"from {module}")
        except Exception as exc:
            fail(label, str(exc))


# ── Section 3: Capability declarations ───────────────────────────────────────

def check_capability_declarations(reg) -> dict:
    """Returns {agent_id: agent_obj} for agents that passed."""
    print(f"\n{BOLD(CYAN('3. Capability declarations'))}\n")
    agents_ok = {}
    for entry in reg.list_agents():
        aid = entry["agent_id"]
        agent = reg.get(aid)
        if agent is None:
            fail(aid, "registered but get() returned None")
            continue

        issues = []
        if not agent.allowed_tools:
            issues.append("allowed_tools not declared")
        if not agent.allowed_endpoints:
            issues.append("allowed_endpoints not declared (warning)")

        if not issues:
            ok(
                aid,
                f"allowed_tools={len(agent.allowed_tools)}  endpoints={len(agent.allowed_endpoints)}",
            )
            agents_ok[aid] = agent
        elif all("warning" in i for i in issues):
            warn(aid, "; ".join(issues))
            agents_ok[aid] = agent
        else:
            fail(aid, "; ".join(issues))

    # Expected agents present?
    for expected in EXPECTED_AGENTS:
        if expected not in {e["agent_id"] for e in reg.list_agents()}:
            fail(f"expected agent missing: {expected!r}")

    return agents_ok


# ── Section 4: Tool registry completeness ────────────────────────────────────

def check_tool_registry(agents_ok: dict, fleet) -> None:
    print(f"\n{BOLD(CYAN('4. Tool registry completeness'))}\n")

    all_declared: list[tuple[str, str]] = []  # (agent_id, tool_name)
    for aid, agent in agents_ok.items():
        for tname in agent.allowed_tools:
            all_declared.append((aid, tname))

    if not all_declared:
        skip("no tools declared by any agent")
        return

    for aid, tname in all_declared:
        if not fleet.is_registered(tname):
            fail(f"{aid} → {tname}", "NOT in fleet tool registry — missing ToolRegistration")
        else:
            reg = fleet.get(tname)
            ok(f"{aid} → {tname}", f"risk_tier={reg.risk_tier}")


# ── Section 5: Risk tier coherence ───────────────────────────────────────────

def check_risk_tier_coherence(fleet) -> None:
    print(f"\n{BOLD(CYAN('5. Risk tier coherence'))}\n")

    tools = fleet.list_tools()
    if not tools:
        skip("no tools in fleet registry")
        return

    for t in tools:
        name = t["name"]
        tier = t["risk_tier"]
        issues = []

        if tier not in RISK_TIERS:
            issues.append(f"unknown risk_tier {tier!r}")
        if t["write_side_effects"] and tier == "read_only":
            issues.append("write_side_effects=True but risk_tier='read_only' — consider 'write'")
        if t["credential_required"] and tier == "read_only":
            issues.append("credential_required=True but risk_tier='read_only' — consider 'credential_use'")
        if t["external_network"] and tier not in ("external_network", "credential_use"):
            issues.append(f"external_network=True but risk_tier={tier!r} — consider 'external_network'")

        if not issues:
            ok(name, tier)
        else:
            for issue in issues:
                warn(name, issue)


# ── Section 6: Prover simulation ─────────────────────────────────────────────

def check_prover_simulation(agents_ok: dict, fleet) -> None:
    print(f"\n{BOLD(CYAN('6. Prover simulation'))}\n")

    for aid, agent in agents_ok.items():
        declared = set(agent.allowed_tools)
        registered_for_agent = set()

        for tname in declared:
            reg = fleet.get(tname)
            if reg is None:
                continue  # already flagged in check 4
            registered_for_agent.add(tname)

            # permitted_agents check
            permitted, reason = fleet.is_permitted(tname, aid)
            if not permitted:
                fail(f"{aid} → {tname}", f"fleet registry DENIED: {reason}")
            else:
                pass  # clean; reported in check 4 already

        # Dead entries in allowed_tools (not registered = already flagged; here check registered names vs actual tool_map)
        tool_map_names = {t.name for t in agent.tools}
        dead = declared - tool_map_names
        if dead:
            warn(f"{aid}", f"dead entries in allowed_tools (no matching AgentTool): {sorted(dead)}")

        # Tools registered but not in allowed_tools
        undeclared = tool_map_names - declared
        if undeclared:
            warn(f"{aid}", f"tools registered but not in allowed_tools (will be blocked): {sorted(undeclared)}")

        if not dead and not undeclared:
            # Check cross-agent: any other agent permitted to use these tools?
            cross = []
            for tname in declared:
                reg = fleet.get(tname)
                if reg is None:
                    continue
                if reg.permitted_agents is not None and reg.permitted_agents != [aid]:
                    others = [a for a in reg.permitted_agents if a != aid]
                    if others:
                        cross.append(f"{tname} shared with {others}")
            if cross:
                warn(f"{aid}", "tools shared with other agents: " + "; ".join(cross))
            else:
                ok(f"{aid}", "all tools exclusive to this agent, no cross-agent grants")


# ── Section 7: Isolation pre-flight ──────────────────────────────────────────

def check_isolation_preflight() -> None:
    print(f"\n{BOLD(CYAN('7. Isolation pre-flight'))}\n")

    if not GOVERNANCE_YAML.exists():
        fail("agent_governance.yaml", f"not found at {GOVERNANCE_YAML} — confirm_isolation() will block all runs")
        return
    try:
        import yaml
        data = yaml.safe_load(GOVERNANCE_YAML.read_text())
        if not isinstance(data, dict):
            fail("agent_governance.yaml", "parsed but top-level is not a dict")
            return
        ok("agent_governance.yaml", f"keys: {', '.join(list(data.keys())[:6])}")
    except Exception as exc:
        fail("agent_governance.yaml", f"parse error: {exc}")

    # Verify the confirm_isolation() method exists on the base class
    try:
        from chatbot.agents.managed.base import ManagedAgent
        if not hasattr(ManagedAgent, "confirm_isolation"):
            fail("ManagedAgent.confirm_isolation()", "method not found on base class")
        else:
            ok("ManagedAgent.confirm_isolation()", "method present on base class")
    except Exception as exc:
        fail("ManagedAgent.confirm_isolation()", str(exc))

    # Verify circuit breaker threshold is sane
    try:
        from chatbot.agents.managed import base as _base
        threshold = getattr(_base, "_SUPERVISOR_VIOLATION_THRESHOLD", None)
        if threshold is None:
            fail("_SUPERVISOR_VIOLATION_THRESHOLD", "not defined in base.py")
        elif not (1 <= threshold <= 10):
            warn("_SUPERVISOR_VIOLATION_THRESHOLD", f"value {threshold} outside sane range 1–10")
        else:
            ok("_SUPERVISOR_VIOLATION_THRESHOLD", str(threshold))
    except Exception as exc:
        fail("_SUPERVISOR_VIOLATION_THRESHOLD", str(exc))


# ── Section 8: DETECT alignment ──────────────────────────────────────────────

def check_detect_alignment() -> None:
    print(f"\n{BOLD(CYAN('8. DETECT alignment'))}\n")

    REQUIRED_RULES = {
        "DETECT-AGT-004": "tool_restriction_bypass — supervisor violations feed this signal",
        "DETECT-AGT-003": "permission_escalation_without_revocation — risk tier escalation path",
        "DETECT-AGT-005": "unscoped_write_action — write-tier tools without minimal footprint guard",
    }

    if not DETECT_RULES.exists():
        fail("soc_detection_rules.yaml", "file not found")
        return

    try:
        content = DETECT_RULES.read_text()
        for rule_id, note in REQUIRED_RULES.items():
            if rule_id in content:
                ok(rule_id, note)
            else:
                fail(rule_id, f"not found in soc_detection_rules.yaml — {note}")
    except Exception as exc:
        fail("soc_detection_rules.yaml", str(exc))


# ── Section 9: Live API ───────────────────────────────────────────────────────

def check_live_api(base_url: str) -> None:
    print(f"\n{BOLD(CYAN('9. Live API'))} — {base_url}\n")
    try:
        import urllib.request
        import urllib.error

        def _get(path: str):
            url = f"{base_url.rstrip('/')}{path}"
            req = urllib.request.Request(url, headers={"Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status, json.loads(resp.read().decode())

        # fleet-posture
        try:
            status, data = _get("/api/v1/agents/fleet-posture")
            if status == 200:
                posture = data.get("posture", "?")
                total   = data.get("total_tools", "?")
                color   = GREEN if posture == "CLEAN" else AMBER if posture in ("WARN", "ELEVATED") else RED
                ok("GET /api/v1/agents/fleet-posture", f"posture={color(posture)}  tools={total}")
                if data.get("policy_conflicts"):
                    for conflict in data["policy_conflicts"]:
                        warn("policy_conflict", f"{conflict.get('agent_id')} → {conflict.get('tool')}: {conflict.get('issue')}")
            else:
                fail("GET /api/v1/agents/fleet-posture", f"HTTP {status}")
        except urllib.error.URLError as exc:
            fail("GET /api/v1/agents/fleet-posture", str(exc))

        # tools catalog
        try:
            status, data = _get("/api/v1/agents/tools")
            if status == 200:
                tools = data.get("tools", [])
                ok(
                    "GET /api/v1/agents/tools",
                    f"{len(tools)} tools  tiers={sorted({t['risk_tier'] for t in tools})}",
                )
            else:
                fail("GET /api/v1/agents/tools", f"HTTP {status}")
        except urllib.error.URLError as exc:
            fail("GET /api/v1/agents/tools", str(exc))

    except Exception as exc:
        fail("live API check", str(exc))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="check-managed-agents")
    parser.add_argument("--live", action="store_true", help="run live API checks")
    parser.add_argument("--url", default="http://localhost:8000", help="API base URL")
    args = parser.parse_args()

    print(f"\n{BOLD('TA Managed Agent Fleet — Posture Check')}")
    print(f"{DIM('repo: ' + str(REPO_ROOT))}")

    t0 = time.time()

    # 1. Syntax
    check_syntax()

    # 2. Imports — boot the fleet early so later checks can use live objects
    check_imports()

    # Load registry + fleet for checks 3–6
    try:
        from chatbot.agents.managed.registry import get_registry
        from chatbot.agents.managed.tool_registry import get_tool_registry
        reg   = get_registry()
        fleet = get_tool_registry()
    except Exception as exc:
        print(f"\n  {RED('✗')}  Cannot load registry/fleet: {exc}")
        print(f"\n{RED(BOLD('FAIL'))}  — could not boot managed agent fleet\n")
        sys.exit(1)

    # 3. Capability declarations
    agents_ok = check_capability_declarations(reg)

    # 4. Tool registry completeness
    check_tool_registry(agents_ok, fleet)

    # 5. Risk tier coherence
    check_risk_tier_coherence(fleet)

    # 6. Prover simulation
    check_prover_simulation(agents_ok, fleet)

    # 7. Isolation pre-flight
    check_isolation_preflight()

    # 8. DETECT alignment
    check_detect_alignment()

    # 9. Live API (optional)
    if args.live:
        check_live_api(args.url)
    else:
        print(f"\n{BOLD(CYAN('9. Live API'))}  {DIM('— skipped (pass --live to enable)')}")

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed = time.time() - t0
    total = passed + failed + warned
    print(f"\n{'─' * 54}")

    if failed > 0:
        verdict = RED(BOLD("FAIL"))
        exit_code = 1
    elif warned > 0:
        verdict = AMBER(BOLD("WARN"))
        exit_code = 0
    else:
        verdict = GREEN(BOLD("PASS"))
        exit_code = 0

    # Fleet posture label from static check
    try:
        posture_data = fleet.get_fleet_posture(agent_registry=reg)
        posture_label = posture_data.get("posture", "UNKNOWN")
        color = GREEN if posture_label == "CLEAN" else AMBER if posture_label in ("WARN", "ELEVATED") else RED
        posture_str = f"  fleet posture={color(posture_label)}"
    except Exception:
        posture_str = ""

    print(
        f"  {verdict}  {passed}/{total} checks passed, "
        f"{warned} warnings, {failed} failures  "
        f"{DIM(f'({elapsed:.1f}s)')}{posture_str}"
    )
    print()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
