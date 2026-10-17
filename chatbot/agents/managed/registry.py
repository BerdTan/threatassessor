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


class ManagedAgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, "ManagedAgent"] = {}

    def register(self, agent: "ManagedAgent") -> None:
        self._agents[agent.agent_id] = agent
        logger.info("ManagedAgentRegistry: registered '%s'", agent.agent_id)

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
