"""
PolicyBroker — dynamic routing decisions from live governance signals.

Called by ThreatAssessorHarness after QualityStage, before CriticStage.
Reads live GovernanceSignals + AIVSSScore and returns a BrokerDecision that
the harness applies to ctx["blocked_agents"] and HarnessModelGuardian.

Design principles:
- Additive: PolicyBroker adds to blocked_agents, never replaces the existing
  governance-policy-derived list from QualityStage.
- Non-fatal: if PolicyBroker.decide() raises, the harness logs and continues
  with the existing blocked_agents unchanged. Robustness > correctness here.
- Auditable: every decision carries a rationale string written to ctx for SIEM.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    pass

_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BrokerDecision
# ---------------------------------------------------------------------------

@dataclass
class BrokerDecision:
    """Output of PolicyBroker.decide(). Applied by ThreatAssessorHarness."""

    # Additional agents to block (merged with existing ctx["blocked_agents"])
    blocked_agents:  List[str] = field(default_factory=list)

    # Per-agent model overrides applied to HarnessModelGuardian
    # e.g. {"blackhat": "claude-haiku-4-5-20251001"} to downgrade on high AIVSS
    model_overrides: Dict[str, str] = field(default_factory=dict)

    # Sink routing tier — controls EventBrokerCritic priority fan-out
    # "critical" → events go to priority sinks (immediate SIEM/page)
    # "normal"   → standard routing
    # "audit_only" → suppress non-essential sinks (debug/webhook) in low-risk mode
    sink_tier: str = "normal"

    # Human-readable rationale for audit log
    rationale: str = ""


# ---------------------------------------------------------------------------
# PolicyBroker
# ---------------------------------------------------------------------------

class PolicyBroker:
    """Evaluates live governance signals and returns a dynamic routing decision.

    Rules are evaluated in priority order; first match wins for blocked_agents
    and sink_tier. model_overrides are accumulated across all matching rules.

    Rules (in priority order):
      1. CRITICAL exploitation.blocked  → block ALL critics, sink_tier=critical
      2. CRITICAL overall_risk_level    → block red_team + blackhat, sink_tier=critical
      3. AIVSS inbound composite >= 7.0 → block red_team + blackhat (attack surface too high)
      4. AIVSS internal composite >= 8.0 → downgrade blackhat to cheaper model
      5. sm_verdicts.acceptance_rate <= 0.4 → sink_tier=critical (reward hacking signal)
      6. Default                          → no changes
    """

    # Agents to block when exploitation is CRITICAL
    _ALL_CRITICS = ["architect", "tester", "red_team", "purple_team", "blackhat"]

    # Cheaper model used when cost-sensitive downgrade is triggered
    _CHEAPER_MODEL = "claude-haiku-4-5-20251001"

    def decide(
        self,
        governance_signals: dict,
        aivss_score: Optional[object] = None,
    ) -> BrokerDecision:
        """Evaluate signals and return a BrokerDecision.

        governance_signals: dict from ctx["governance_signals"]
        aivss_score: AIVSSScore object from ctx["_aivss_score"] (may be None
                     at the point PolicyBroker is called — pre-AIVSSStage)
        """
        decision = BrokerDecision()
        rationale_parts: List[str] = []

        exploit = governance_signals.get("exploitation", {})
        manip   = governance_signals.get("manipulation", {})
        overall = governance_signals.get("overall_risk_level", "LOW")

        # ── Rule 1: CRITICAL exploitation.blocked ────────────────────────────
        if exploit.get("blocked") is True:
            decision.blocked_agents = list(self._ALL_CRITICS)
            decision.sink_tier      = "critical"
            rationale_parts.append("exploitation.blocked=True → all critics blocked")
            _log.warning("PolicyBroker: ALL critics blocked (exploitation.blocked=True)")

        # ── Rule 2: CRITICAL overall_risk_level ──────────────────────────────
        elif overall == "CRITICAL":
            decision.blocked_agents = ["red_team", "blackhat"]
            decision.sink_tier      = "critical"
            rationale_parts.append("overall_risk_level=CRITICAL → red_team+blackhat blocked")

        # ── Rule 3: AIVSS inbound composite >= 7.0 ───────────────────────────
        else:
            inbound = governance_signals.get("aivss", {}).get("inbound", {})
            if isinstance(inbound, dict):
                inbound_composite = float(inbound.get("composite", 0.0) or 0.0)
                if inbound_composite >= 7.0:
                    for agent in ["red_team", "blackhat"]:
                        if agent not in decision.blocked_agents:
                            decision.blocked_agents.append(agent)
                    if decision.sink_tier == "normal":
                        decision.sink_tier = "critical"
                    rationale_parts.append(
                        f"AIVSS inbound {inbound_composite:.1f} >= 7.0 → red_team+blackhat blocked"
                    )

        # ── Rule 4: AIVSS internal composite >= 8.0 → downgrade blackhat ─────
        if "blackhat" not in decision.blocked_agents:
            internal = governance_signals.get("aivss", {}).get("internal", {})
            if isinstance(internal, dict):
                internal_composite = float(internal.get("composite", 0.0) or 0.0)
                if internal_composite >= 8.0:
                    decision.model_overrides["blackhat"] = self._CHEAPER_MODEL
                    rationale_parts.append(
                        f"AIVSS internal {internal_composite:.1f} >= 8.0 → blackhat downgraded"
                    )

        # ── Rule 5: SM acceptance_rate <= 0.4 → escalate sink tier ───────────
        sm = governance_signals.get("sm_verdicts", {})
        if sm:
            rate = sm.get("acceptance_rate")
            if rate is not None and float(rate) <= 0.4 and not sm.get("redesign_signal", False):
                if decision.sink_tier == "normal":
                    decision.sink_tier = "critical"
                rationale_parts.append(
                    f"sm_verdicts.acceptance_rate={rate} <= 0.4 → sink_tier escalated"
                )

        decision.rationale = "; ".join(rationale_parts) if rationale_parts else "no policy match"
        return decision
