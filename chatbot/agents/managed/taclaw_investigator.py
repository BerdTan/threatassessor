"""
TAclawInvestigationAgent — managed agent that activates on gate=BLOCK.

Given a blocked TAclaw result, the agent uses its tools to:
  1. Identify which Bouncer check / DETECT rules fired
  2. Query the TA Brain for historical patterns on this arch type
  3. Look up rule details (kill chain, MITRE, remediations)
  4. Optionally inspect the pipeline quality context
  5. Synthesize a structured remediation plan

Jev gate (point 9): noul check before launch — trivial blocks (kill_switch,
explicit deny-list) skip the agent and return a fast reason instead.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from chatbot.agents.managed.base import AgentTool, ManagedAgent

logger = logging.getLogger(__name__)

_RULES_PATH = Path(__file__).resolve().parents[3] / "policies" / "soc_detection_rules.yaml"
_BRAIN_PATH = Path(__file__).resolve().parents[3] / "report" / "brain" / "ta_brain.json"


# ── helpers ───────────────────────────────────────────────────────────────────

def _load_rules() -> Dict[str, Dict]:
    """Return {rule_id: rule_dict} from soc_detection_rules.yaml."""
    try:
        import yaml
        data = yaml.safe_load(_RULES_PATH.read_text())
        return {r["id"]: r for r in data.get("rules", [])}
    except Exception as exc:
        logger.warning("TAclawInvestigator: could not load rules: %s", exc)
        return {}


def _load_brain() -> Dict[str, Any]:
    try:
        return json.loads(_BRAIN_PATH.read_text())
    except Exception as exc:
        logger.warning("TAclawInvestigator: could not load brain: %s", exc)
        return {}


# ── Bouncer check taxonomy ────────────────────────────────────────────────────

_BOUNCER_CHECKS = {
    "exploitation.blocked=True": {
        "label": "Critical injection / traversal detected in input",
        "kill_chain": "Initial Access / Execution",
        "remediation_hint": "Review input sanitisation; check for prompt injection or path traversal in architecture description.",
    },
    "_outbound_blocked": {
        "label": "AIVSS outbound gate tripped on prior run",
        "kill_chain": "Exfiltration",
        "remediation_hint": "Prior AIVSS composite score dropped below threshold. Inspect AIVSS delta in the pipeline context.",
    },
    "kill_switch": {
        "label": "Global kill-switch enabled in agent_governance.yaml",
        "kill_chain": "Policy override",
        "remediation_hint": "kill_switch=True in policies/agent_governance.yaml. Disable only after governance review.",
    },
    "blocked_architectures": {
        "label": "Architecture name is on the explicit deny list",
        "kill_chain": "Policy override",
        "remediation_hint": "Remove the arch name from blocked_architectures in policies/agent_governance.yaml after review.",
    },
    "preflight_authority_gate": {
        "label": "Pre-flight authority gate failed (independent Jev signal)",
        "kill_chain": "Privilege Escalation",
        "remediation_hint": "Jev noul score below authority threshold on governance pre-flight. Review governance signals.",
    },
    "agentic_architecture_no_oversight_path": {
        "label": "Agentic architecture declared with no human oversight path",
        "kill_chain": "Persistence / Defense Evasion",
        "remediation_hint": "Add a human-in-the-loop checkpoint or approval gate to the architecture before re-running.",
    },
}


# ── agent ─────────────────────────────────────────────────────────────────────

class TAclawInvestigationAgent(ManagedAgent):
    agent_id = "taclaw_investigator"
    description = "Investigates gate=BLOCK outcomes: identifies root signals, queries brain patterns, produces remediation plan."
    max_iterations = 8

    system_prompt = """You are a security investigation agent for ThreatAssessor.

A TAclaw threat model assessment has been BLOCKED by the pipeline's Bouncer gate or a Critical DETECT rule.
Your job is to investigate what happened and produce a clear, actionable remediation plan.

Use your tools in this order:
1. get_block_signals — understand exactly what triggered the block
2. query_brain_patterns — check if this block type is a known pattern for this architecture class
3. get_rule_detail — for each DETECT rule that fired at Critical/High, get its kill chain and remediation hints
4. get_pipeline_context — if you need quality scores, AIVSS delta, or critic verdicts for context
5. synthesize_remediation — once you have enough information, call this to produce the final report

Be concise and specific. Do not speculate beyond what the signals tell you.
When you are ready to produce the final report, call synthesize_remediation with your findings.
Your final answer after calling synthesize_remediation should be the JSON output from that tool, unchanged."""

    def _register_tools(self) -> None:
        self._add_tool(AgentTool(
            name="get_block_signals",
            description="Returns the Bouncer check that fired and any Critical/High DETECT rules from the TAclaw result.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "TAclaw job ID"},
                },
                "required": ["job_id"],
            },
            handler=self._tool_get_block_signals,
        ))
        self._add_tool(AgentTool(
            name="query_brain_patterns",
            description="Look up historical threat patterns in the TA Brain for a given architecture type and optional signal key.",
            input_schema={
                "type": "object",
                "properties": {
                    "arch_type": {"type": "string", "description": "Architecture type, e.g. 'agentic_ai', 'microservices'"},
                    "signal_key": {"type": "string", "description": "Optional DETECT rule id or Bouncer check key to filter patterns"},
                },
                "required": ["arch_type"],
            },
            handler=self._tool_query_brain_patterns,
        ))
        self._add_tool(AgentTool(
            name="get_rule_detail",
            description="Get full details for a DETECT rule: description, kill chain stage, MITRE techniques, CSA ART tags, remediation tuning note.",
            input_schema={
                "type": "object",
                "properties": {
                    "rule_id": {"type": "string", "description": "DETECT rule id, e.g. 'DETECT-QC-001'"},
                },
                "required": ["rule_id"],
            },
            handler=self._tool_get_rule_detail,
        ))
        self._add_tool(AgentTool(
            name="get_pipeline_context",
            description="Returns AIVSS score, quality score, critic verdicts, and governance signals for the blocked job.",
            input_schema={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string", "description": "TAclaw job ID"},
                },
                "required": ["job_id"],
            },
            handler=self._tool_get_pipeline_context,
        ))
        self._add_tool(AgentTool(
            name="synthesize_remediation",
            description="Produce the final structured remediation report. Call this once you have gathered sufficient context.",
            input_schema={
                "type": "object",
                "properties": {
                    "block_summary": {"type": "string", "description": "One sentence: what blocked and why"},
                    "root_signals": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of rule IDs or Bouncer check keys that are the root cause",
                    },
                    "brain_context": {"type": "string", "description": "What brain patterns revealed (or 'no prior patterns found')"},
                    "remediation_steps": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Ordered list of specific remediation actions",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["high", "medium", "low"],
                        "description": "Confidence in the remediation plan given available signal",
                    },
                },
                "required": ["block_summary", "root_signals", "brain_context", "remediation_steps", "confidence"],
            },
            handler=self._tool_synthesize_remediation,
        ))

    # ── tool handlers ─────────────────────────────────────────────────────────

    def _tool_get_block_signals(self, inp: Dict[str, Any]) -> str:
        ctx = self._context  # injected by run() override
        result = ctx.get("pipeline_result", {})

        bouncer_reason = ctx.get("bouncer_reason", "unknown")
        check_info = _BOUNCER_CHECKS.get(bouncer_reason, {
            "label": bouncer_reason,
            "kill_chain": "Unknown",
            "remediation_hint": "Inspect pipeline logs for more detail.",
        })

        fired_rules = ctx.get("fired_detect_rules", [])

        return json.dumps({
            "bouncer_check": bouncer_reason,
            "bouncer_label": check_info["label"],
            "bouncer_kill_chain": check_info["kill_chain"],
            "bouncer_remediation_hint": check_info["remediation_hint"],
            "detect_rules_fired": fired_rules,
            "arch_name": ctx.get("arch_name", ""),
            "arch_type": ctx.get("arch_type", ""),
        })

    def _tool_query_brain_patterns(self, inp: Dict[str, Any]) -> str:
        arch_type: str = inp.get("arch_type", "")
        signal_key: str = inp.get("signal_key", "")

        brain = _load_brain()
        patterns = brain.get("patterns", [])

        matched = []
        for p in patterns:
            arch_match = not arch_type or arch_type.lower() in str(p.get("arch_types", [])).lower()
            sig_match = not signal_key or signal_key.lower() in json.dumps(p).lower()
            if arch_match and sig_match:
                matched.append({
                    "id": p.get("id", ""),
                    "arch_types": p.get("arch_types", []),
                    "frequency": p.get("frequency", 0),
                    "top_techniques": p.get("top_techniques", [])[:5],
                    "top_components": p.get("top_components", [])[:5],
                })

        return json.dumps({
            "arch_type_queried": arch_type,
            "signal_filter": signal_key,
            "patterns_found": len(matched),
            "patterns": matched[:5],  # top 5 to keep context tight
        })

    def _tool_get_rule_detail(self, inp: Dict[str, Any]) -> str:
        rule_id: str = inp.get("rule_id", "")
        rules = _load_rules()
        rule = rules.get(rule_id)
        if not rule:
            return json.dumps({"error": f"Rule {rule_id!r} not found"})
        return json.dumps({
            "id": rule.get("id"),
            "name": rule.get("name"),
            "domain": rule.get("domain"),
            "severity": rule.get("severity"),
            "description": rule.get("description"),
            "kill_chain_stage": rule.get("kill_chain_stage"),
            "atlas_tactic": rule.get("atlas_tactic"),
            "owasp": rule.get("owasp"),
            "csa_art": rule.get("csa_art"),
            "tuning_note": rule.get("tuning_note"),
        })

    def _tool_get_pipeline_context(self, inp: Dict[str, Any]) -> str:
        ctx = self._context
        result = ctx.get("pipeline_result", {})
        return json.dumps({
            "aivss_score": result.get("aivss_score"),
            "quality_score": result.get("quality_score"),
            "routing_mode": result.get("routing_mode"),
            "governance_flags": result.get("governance_flags", {}),
            "critic_summary": result.get("critic_summary", {}),
        })

    def _tool_synthesize_remediation(self, inp: Dict[str, Any]) -> str:
        # The agent calls this as its final step — we capture and return it structured
        report = {
            "block_summary": inp.get("block_summary", ""),
            "root_signals": inp.get("root_signals", []),
            "brain_context": inp.get("brain_context", ""),
            "remediation_steps": inp.get("remediation_steps", []),
            "confidence": inp.get("confidence", "low"),
            "agent_id": self.agent_id,
        }
        # Store for _parse_output to return
        self._synthesis_result = report
        return json.dumps({"status": "synthesis_complete", "report": report})

    # ── should_run: fast checks + Jev gate ───────────────────────────────────

    def should_run(self, context: Dict[str, Any]) -> Tuple[bool, str]:
        if context.get("gate") != "BLOCK":
            return False, "gate not BLOCK"

        bouncer_reason = context.get("bouncer_reason", "")

        # kill_switch and explicit deny-list are self-explanatory — skip agent
        if bouncer_reason in ("kill_switch", "blocked_architectures"):
            return False, f"trivial_block:{bouncer_reason}"

        # Jev gate (point 9): is investigation worth the token cost?
        try:
            from chatbot.modules.jev_client import get_jev_client
            jev = get_jev_client()
            if jev.is_enabled():
                r = jev.noul(
                    instructions="Should a full managed investigation agent be launched to analyse this security block and produce a remediation plan?",
                    state={
                        "bouncer_reason": bouncer_reason,
                        "fired_detect_rules": context.get("fired_detect_rules", []),
                        "max_severity": context.get("max_severity", ""),
                        "arch_type": context.get("arch_type", ""),
                    },
                )
                if r.noul < 0.30:
                    return False, f"jev_gate:noul={r.noul:.2f}"
                logger.debug("TAclawInvestigator: Jev gate passed noul=%.2f", r.noul)
        except Exception as exc:
            logger.debug("TAclawInvestigator: Jev gate skipped (%s)", exc)

        return True, "ok"

    # ── run override: inject context + capture synthesis ─────────────────────

    def run(self, context: Dict[str, Any]) -> "ManagedAgentResult":  # type: ignore[override]
        self._context = context
        self._synthesis_result: Optional[Dict[str, Any]] = None
        result = super().run(context)
        # If agent called synthesize_remediation, use that as the authoritative output
        if self._synthesis_result and result.success:
            result.output = self._synthesis_result
        return result

    def build_task(self, context: Dict[str, Any]) -> str:
        arch = context.get("arch_name", "unknown")
        reason = context.get("bouncer_reason", "unknown")
        rules = context.get("fired_detect_rules", [])
        rule_str = ", ".join(rules) if rules else "none"
        return (
            f"TAclaw assessment for architecture '{arch}' was BLOCKED.\n"
            f"Bouncer check fired: {reason}\n"
            f"DETECT rules fired: {rule_str}\n\n"
            f"Investigate what triggered this block, check brain patterns, "
            f"look up relevant rule details, and produce a specific remediation plan. "
            f"Use job_id='{context.get('job_id', '')}' when tools ask for it."
        )
