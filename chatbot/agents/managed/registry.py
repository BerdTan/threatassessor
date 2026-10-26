"""
ManagedAgentRegistry — singleton fleet registry.

Adding a new agent:
  1. Create chatbot/agents/managed/your_agent.py (subclass ManagedAgent)
  2. Add one line in _auto_register() below

The registry is lazy-initialised on first get_registry() call.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from chatbot.agents.managed.base import ManagedAgent

logger = logging.getLogger(__name__)

_registry: Optional["ManagedAgentRegistry"] = None


def _prove_agent(agent: "ManagedAgent") -> None:
    """
    Lightweight policy prover — runs at registration, not at runtime.
    Flags capability declaration gaps and risky endpoint patterns.
    Mirrors the OpenShell policy prover that checks what a policy change would grant
    before it is applied. Findings are warnings, not hard blocks, so existing agents
    that predate the contract can still register (with noise).
    """
    aid = agent.agent_id

    # ── Capability declaration completeness ───────────────────────────────────
    if not agent.allowed_tools:
        logger.warning(
            "PROVER[%s]: allowed_tools not declared — supervisor enforcement disabled. "
            "Declare allowed_tools to enable per-tool allowlist enforcement.",
            aid,
        )
    else:
        # Flag tools declared on the agent but missing from allowed_tools
        registered = {t.name for t in agent.tools}
        undeclared = registered - set(agent.allowed_tools)
        if undeclared:
            logger.warning(
                "PROVER[%s]: tools registered but NOT in allowed_tools (will be blocked at runtime): %s",
                aid, sorted(undeclared),
            )
        extra = set(agent.allowed_tools) - registered
        if extra:
            logger.warning(
                "PROVER[%s]: allowed_tools names not matched by any registered tool (dead entries): %s",
                aid, sorted(extra),
            )

    if not agent.allowed_endpoints:
        logger.warning(
            "PROVER[%s]: allowed_endpoints not declared — no HTTP endpoint policy for this agent.",
            aid,
        )
    else:
        # Flag endpoints that are not local — potential external data exfiltration surface.
        external = [
            ep for ep in agent.allowed_endpoints
            if not any(ep.startswith(prefix) for prefix in (
                "http://localhost", "http://127.0.0.1",
                "https://localhost", "https://127.0.0.1",
            ))
        ]
        if external:
            logger.warning(
                "PROVER[%s]: allowed_endpoints includes non-localhost destinations — "
                "requires explicit governance approval: %s",
                aid, external,
            )


class ManagedAgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, "ManagedAgent"] = {}

    def register(self, agent: "ManagedAgent") -> None:
        _prove_agent(agent)
        self._agents[agent.agent_id] = agent
        logger.info(
            "ManagedAgentRegistry: registered '%s' (tools=%d, allowed_tools=%d, allowed_endpoints=%d)",
            agent.agent_id, len(agent.tools), len(agent.allowed_tools), len(agent.allowed_endpoints),
        )

    def get(self, agent_id: str) -> Optional["ManagedAgent"]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[Dict[str, str]]:
        return [
            {"agent_id": a.agent_id, "description": a.description}
            for a in self._agents.values()
        ]


def _auto_register(registry: ManagedAgentRegistry) -> None:
    """Register all known agents. Add one import+register line per new agent."""
    from chatbot.agents.managed.taclaw_investigator import TAclawInvestigationAgent
    registry.register(TAclawInvestigationAgent())


def get_registry() -> ManagedAgentRegistry:
    global _registry
    if _registry is None:
        _registry = ManagedAgentRegistry()
        _auto_register(_registry)
    return _registry
