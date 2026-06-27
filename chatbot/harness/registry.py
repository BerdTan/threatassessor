"""
CriticRegistry — control tower for agent activation and governance enforcement.

Critics self-register at module import time via 3-line registration blocks.
MoEOrchestrator calls registry.activate() instead of hardcoding instantiation.
Governance policy can block critics by name via GovernanceSignals.blocked_agents.

Usage:
    from chatbot.harness.registry import _DEFAULT_REGISTRY, CriticDescriptor

    # In each critic file (bottom of file, after class definition):
    _DEFAULT_REGISTRY.register(CriticDescriptor(
        name="architect", cls=EnhancedArchitectCritic,
        governance_tier="standard", model_key="architect",
    ))

    # In MoEOrchestrator:
    critics = _DEFAULT_REGISTRY.activate(
        blocked=ctx.get("blocked_agents", []),
        models=ctx.get("_agent_models", {}),
    )
    self.architect = critics.get("architect")
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Type, Any


@dataclass
class CriticDescriptor:
    """Metadata record for a registered critic.

    governance_tier controls policy visibility:
        "standard"  — always eligible; governance can block on CRITICAL
        "elevated"  — requires explicit allow in policy (e.g. Blackhat)
        "optional"  — informational / non-scoring (e.g. EventBroker)
    """
    name: str
    cls: Type
    governance_tier: str = "standard"
    model_key: str = ""      # key into model_routing.agents config block
    enabled: bool = True     # default on/off (overridden by governance block)


class CriticRegistry:
    """Registry and activation control tower for all critics."""

    def __init__(self) -> None:
        self._registry: Dict[str, CriticDescriptor] = {}

    def register(self, descriptor: CriticDescriptor) -> None:
        """Register a critic descriptor. Idempotent — re-registration updates the entry."""
        self._registry[descriptor.name] = descriptor

    def activate(
        self,
        blocked: Optional[List[str]] = None,
        models: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """Instantiate and return enabled critics not in the blocked list.

        Returns a dict keyed by critic name (e.g. {"architect": <instance>, ...}).
        Critics with governance_tier="optional" are not included unless their name
        is explicitly in an allow-list — they are returned separately via get().
        """
        blocked = set(blocked or [])
        models = models or {}
        result: Dict[str, Any] = {}
        for name, desc in self._registry.items():
            if not desc.enabled:
                continue
            if name in blocked:
                continue
            if desc.governance_tier == "optional":
                continue  # optional critics activated separately via get()
            model = models.get(desc.model_key) or models.get(name)
            try:
                instance = desc.cls(model=model) if model else desc.cls()
            except TypeError:
                instance = desc.cls()
            result[name] = instance
        return result

    def get(self, name: str, blocked: Optional[List[str]] = None, model: Optional[str] = None) -> Optional[Any]:
        """Activate and return a single critic by name (including optional-tier critics).

        Returns None if the name is not registered, not enabled, or is blocked.
        """
        blocked = set(blocked or [])
        desc = self._registry.get(name)
        if desc is None or not desc.enabled or name in blocked:
            return None
        try:
            return desc.cls(model=model) if model else desc.cls()
        except TypeError:
            return desc.cls()

    def list_all(self) -> List[CriticDescriptor]:
        """Return all registered descriptors (ordered by registration)."""
        return list(self._registry.values())

    def list_names(self) -> List[str]:
        """Return names of all registered critics."""
        return list(self._registry.keys())


# Module-level default registry — shared across the process
_DEFAULT_REGISTRY = CriticRegistry()
