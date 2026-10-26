"""
ManagedToolRegistry — fleet-wide tool governance catalog.

Each tool used by any managed agent must be registered here with:
  - risk_tier: escalating risk classification (read_only → write → credential_use → external_network)
  - permitted_agents: None = any agent may use; list = explicit allowlist
  - write_side_effects: True if the tool mutates state (file/DB/API POST-PUT-DELETE)
  - credential_required: True if the tool consumes a real credential
  - external_network: True if the tool reaches a non-localhost endpoint
  - csa_art: CSA ART article(s) that govern this tool's risk posture

This registry is the authoritative governance layer. Per-agent allowed_tools is the
enforcement layer. The two work together:
  - Registry = what exists and who may use it (CISO-auditable)
  - allowed_tools = what a specific agent has declared it needs (supervisor-enforced)

A tool not in the registry cannot be declared in any agent's allowed_tools.
A tool in the registry with a non-empty permitted_agents list can only be declared
by agents in that list.

get_fleet_posture() produces the CISO summary: tool count, risk distribution, per-agent
risk ceiling, write/credential/network flags, and any policy conflicts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

RiskTier = Literal["read_only", "write", "credential_use", "external_network"]

# Risk tier ordering for ceiling calculation
_RISK_ORDER: Dict[str, int] = {
    "read_only": 0,
    "write": 1,
    "credential_use": 2,
    "external_network": 3,
}


@dataclass
class ToolRegistration:
    """Governance metadata for one tool in the fleet catalog."""
    name: str
    description: str
    risk_tier: RiskTier
    write_side_effects: bool = False
    credential_required: bool = False
    external_network: bool = False
    # None = any agent may use; non-empty list = explicit per-agent allowlist
    permitted_agents: Optional[List[str]] = None
    # CSA ART articles that ground this tool's risk classification
    csa_art: List[str] = field(default_factory=list)
    # Which agent registered this tool
    registered_by: str = ""

    def __post_init__(self) -> None:
        # Coherence: flags must be consistent with tier
        if self.external_network and self.risk_tier not in ("external_network", "credential_use"):
            logger.warning(
                "ToolRegistration[%s]: external_network=True but risk_tier=%r — "
                "consider risk_tier='external_network'",
                self.name, self.risk_tier,
            )
        if self.credential_required and self.risk_tier == "read_only":
            logger.warning(
                "ToolRegistration[%s]: credential_required=True but risk_tier='read_only' — "
                "consider risk_tier='credential_use'",
                self.name,
            )


class ManagedToolRegistry:
    """Fleet-wide tool governance catalog. Singleton via get_tool_registry()."""

    def __init__(self) -> None:
        self._tools: Dict[str, ToolRegistration] = {}

    def register(self, reg: ToolRegistration) -> None:
        """
        Register a tool in the fleet catalog.
        Idempotent if risk_tier matches; raises on conflicting re-registration.
        """
        existing = self._tools.get(reg.name)
        if existing is not None:
            if existing.risk_tier != reg.risk_tier:
                raise ValueError(
                    f"ToolRegistry: conflicting risk_tier for {reg.name!r}: "
                    f"already registered as {existing.risk_tier!r}, "
                    f"new registration is {reg.risk_tier!r}. "
                    f"Update the existing registration explicitly."
                )
            # Same tier — idempotent, log at DEBUG
            logger.debug("ToolRegistry: %r already registered (idempotent)", reg.name)
            return
        self._tools[reg.name] = reg
        logger.info(
            "ToolRegistry: registered %r risk_tier=%s write=%s cred=%s net=%s permitted=%s",
            reg.name, reg.risk_tier,
            reg.write_side_effects, reg.credential_required, reg.external_network,
            reg.permitted_agents if reg.permitted_agents is not None else "any",
        )

    def is_registered(self, tool_name: str) -> bool:
        return tool_name in self._tools

    def is_permitted(self, tool_name: str, agent_id: str) -> tuple[bool, str]:
        """
        Check whether agent_id may use tool_name.
        Returns (permitted, reason).
        """
        reg = self._tools.get(tool_name)
        if reg is None:
            return False, f"tool {tool_name!r} not registered in fleet tool registry"
        if reg.permitted_agents is not None and agent_id not in reg.permitted_agents:
            return False, (
                f"tool {tool_name!r} has permitted_agents={reg.permitted_agents!r}; "
                f"agent {agent_id!r} is not in the allowlist"
            )
        return True, "ok"

    def get(self, tool_name: str) -> Optional[ToolRegistration]:
        return self._tools.get(tool_name)

    def list_tools(self) -> List[Dict]:
        return [
            {
                "name": r.name,
                "risk_tier": r.risk_tier,
                "write_side_effects": r.write_side_effects,
                "credential_required": r.credential_required,
                "external_network": r.external_network,
                "permitted_agents": r.permitted_agents,
                "csa_art": r.csa_art,
                "registered_by": r.registered_by,
            }
            for r in self._tools.values()
        ]

    def get_fleet_posture(self, agent_registry: Optional[object] = None) -> Dict:
        """
        Produce a CISO-readable fleet posture summary.
        Optionally accepts the ManagedAgentRegistry to cross-reference agent declarations.
        """
        if not self._tools:
            return {
                "total_tools": 0,
                "risk_distribution": {},
                "agents": [],
                "policy_conflicts": [],
                "posture": "EMPTY",
                "posture_note": "No tools registered in fleet tool registry.",
            }

        # ── risk distribution ─────────────────────────────────────────────────
        risk_dist: Dict[str, int] = {t: 0 for t in _RISK_ORDER}
        for reg in self._tools.values():
            risk_dist[reg.risk_tier] = risk_dist.get(reg.risk_tier, 0) + 1
        # drop zero-count tiers for brevity
        risk_dist = {k: v for k, v in risk_dist.items() if v > 0}

        # ── per-agent summary ─────────────────────────────────────────────────
        agents_summary: List[Dict] = []
        policy_conflicts: List[Dict] = []

        if agent_registry is not None:
            for entry in agent_registry.list_agents():
                aid = entry["agent_id"]
                agent_obj = agent_registry.get(aid)
                if agent_obj is None:
                    continue

                declared = list(agent_obj.allowed_tools)
                if not declared:
                    continue

                # risk ceiling = highest risk_tier among declared tools that are registered
                ceiling = "read_only"
                has_write = False
                has_cred = False
                has_net = False
                for tname in declared:
                    reg = self._tools.get(tname)
                    if reg is None:
                        policy_conflicts.append({
                            "agent_id": aid,
                            "tool": tname,
                            "issue": "tool declared in allowed_tools but not in fleet registry",
                        })
                        continue
                    if _RISK_ORDER.get(reg.risk_tier, 0) > _RISK_ORDER.get(ceiling, 0):
                        ceiling = reg.risk_tier
                    has_write = has_write or reg.write_side_effects
                    has_cred = has_cred or reg.credential_required
                    has_net = has_net or reg.external_network
                    permitted, reason = self.is_permitted(tname, aid)
                    if not permitted:
                        policy_conflicts.append({
                            "agent_id": aid,
                            "tool": tname,
                            "issue": reason,
                        })

                agents_summary.append({
                    "agent_id": aid,
                    "tool_count": len(declared),
                    "risk_ceiling": ceiling,
                    "write_side_effects": has_write,
                    "credential_required": has_cred,
                    "external_network": has_net,
                })

        # ── overall posture ───────────────────────────────────────────────────
        has_external = any(r.external_network for r in self._tools.values())
        has_write = any(r.write_side_effects for r in self._tools.values())
        has_cred = any(r.credential_required for r in self._tools.values())

        if policy_conflicts:
            posture = "VIOLATION"
            posture_note = f"{len(policy_conflicts)} policy conflict(s) — agents using tools outside their permitted scope."
        elif has_external or has_cred:
            posture = "ELEVATED"
            posture_note = "Fleet includes tools with external network or credential access."
        elif has_write:
            posture = "WARN"
            posture_note = "Fleet includes tools with write side-effects."
        else:
            posture = "CLEAN"
            posture_note = "All tools are read-only, localhost-only, and require no credentials."

        return {
            "total_tools": len(self._tools),
            "risk_distribution": risk_dist,
            "agents": agents_summary,
            "policy_conflicts": policy_conflicts,
            "posture": posture,
            "posture_note": posture_note,
        }


_tool_registry: Optional[ManagedToolRegistry] = None


def get_tool_registry() -> ManagedToolRegistry:
    global _tool_registry
    if _tool_registry is None:
        _tool_registry = ManagedToolRegistry()
    return _tool_registry
