"""
Architect Critic Agent - Validation-Only Mode (Phase 3D)

Role: Security Architect validating threat assessment design quality

VALIDATION-ONLY CONTRACT:
- Does NOT generate new threats or controls
- Does NOT override deterministic analysis (ground_truth.json)
- VALIDATES quality of existing threat model and control recommendations
- Returns confidence adjustment (-0% to -10%) based on validation gaps
- Focus: "Is this analysis good?" NOT "What should we analyze?"

Prerequisites (fail-fast):
- ground_truth.json MUST exist (from deterministic analysis)
- All 10 artifacts MUST be present (enforced by MoEOrchestrator)

Rubric (100 points):
- Tier 1 (80 points): Critical artifacts from ground_truth.json
  - Threat Model Completeness (30 points)
  - Control Appropriateness (25 points)
  - Defense-in-Depth (15 points)
  - RAPIDS Alignment (10 points)
- Tier 2 (20 points): Important artifacts from report files
  - Diagram Completeness (10 points) - after.mmd validation
  - Report Quality (10 points) - technical + executive + action plan

Output: CritiqueScore with validation gaps and confidence adjustment

VERSION: 3.0 - Phase 3D Week 2 (Validation-only refactor)
"""

import logging
from typing import Dict, List, Optional

from chatbot.modules.agent_framework import CriticAgent, AgentTool
from chatbot.modules.artifact_extractor import ArtifactSet

logger = logging.getLogger(__name__)


# ============================================================================
# ARCHITECT TOOLS
# ============================================================================

def search_control_context(control_name: str, architecture_type: str) -> str:
    """
    Search for control best practices in given architecture context.

    Args:
        control_name: Control to research (e.g., "WAF", "MFA")
        architecture_type: Architecture type (e.g., "web_app", "ai_system")

    Returns: Context-specific guidance
    """
    # MVP1: Simple lookup (can be enhanced with actual search later)
    context_map = {
        "web_app": {
            "waf": "Critical for web applications - blocks OWASP Top 10 attacks at perimeter",
            "mfa": "Highly relevant - mitigates credential theft from phishing",
            "rate limiting": "Essential for API protection and DoS prevention"
        },
        "ai_system": {
            "prompt filtering": "Critical for AI - prevents prompt injection and jailbreaks",
            "rate limiting": "Essential for AI - prevents model abuse and cost overruns",
            "sandbox": "Important for AI - isolates model execution"
        },
        "iot": {
            "network segmentation": "Critical for IoT - prevents lateral movement",
            "firmware validation": "Essential for IoT - prevents device compromise",
            "certificate management": "Important for IoT - ensures device identity"
        }
    }

    arch_controls = context_map.get(architecture_type, {})
    guidance = arch_controls.get(control_name.lower(), "General security control - verify applicability to architecture")

    return guidance


def check_architecture_type(components: List[str]) -> str:
    """
    Identify architecture type from components.

    Args:
        components: List of component names

    Returns: Architecture type (web_app, ai_system, iot, generic)
    """
    components_lower = [c.lower() for c in components]

    # AI/LLM indicators
    if any(kw in ' '.join(components_lower) for kw in ['llm', 'agent', 'model', 'embedding', 'vectordb']):
        return "ai_system"

    # IoT indicators
    if any(kw in ' '.join(components_lower) for kw in ['sensor', 'device', 'gateway', 'mqtt', 'firmware']):
        return "iot"

    # Web app indicators (default if has internet + database)
    if any(kw in ' '.join(components_lower) for kw in ['web', 'api', 'http', 'rest']):
        return "web_app"

    return "generic"


# ============================================================================
# ARCHITECT RUBRIC
# ============================================================================

ARCHITECT_RUBRIC = {
    # TIER 1: Critical artifacts (80 points)
    "threat_completeness": {
        "max": 30,
        "tier": 1,
        "criteria": {
            "entry_points": {"points": 8, "description": "All entry points identified"},
            "data_flows": {"points": 7, "description": "All data flows mapped"},
            "arch_specific_threats": {"points": 8, "description": "Architecture-specific threats considered"},
            "trust_boundaries": {"points": 7, "description": "Trust boundaries clearly defined"}
        }
    },
    "control_appropriateness": {
        "max": 25,
        "tier": 1,
        "criteria": {
            "complexity_match": {"points": 8, "description": "Controls match architecture complexity"},
            "sensitivity_alignment": {"points": 9, "description": "Controls aligned with data sensitivity"},
            "feasibility": {"points": 8, "description": "Controls feasible for architecture type"}
        }
    },
    "defense_in_depth": {
        "max": 15,
        "tier": 1,
        "criteria": {
            "multiple_layers": {"points": 8, "description": "Multiple control layers per path"},
            "no_spof": {"points": 7, "description": "No single points of failure unmitigated"}
        }
    },
    "rapids_alignment": {
        "max": 10,
        "tier": 1,
        "criteria": {
            "threat_coverage": {"points": 5, "description": "All 6 RAPIDS categories addressed"},
            "risk_prioritization": {"points": 5, "description": "Controls prioritized by risk score"}
        }
    },
    # TIER 2: Important artifacts (20 points)
    "diagram_completeness": {
        "max": 10,
        "tier": 2,
        "criteria": {
            "after_mmd_controls": {"points": 7, "description": "All controls visualized in after.mmd"},
            "visual_clarity": {"points": 3, "description": "Diagram is clear and readable"}
        }
    },
    "report_quality": {
        "max": 10,
        "tier": 2,
        "criteria": {
            "technical_depth": {"points": 4, "description": "Technical report has sufficient detail"},
            "executive_clarity": {"points": 3, "description": "Executive summary is business-friendly"},
            "action_plan_feasibility": {"points": 3, "description": "Action plan is realistic and phased"}
        }
    }
}


# ============================================================================
# ARCHITECT SYSTEM PROMPT
# ============================================================================

ARCHITECT_SYSTEM_PROMPT = """You are a Senior Security Architect reviewing a threat assessment.

IMPORTANT: This prompt uses explicit terminology to avoid ambiguity.

============================================================
DEFINITIONS (spell out all terms)
============================================================

RAPIDS: Six risk areas used for threat assessment
- R: Ransomware (risk of ransomware/data encryption attacks)
- A: Application vulnerabilities (web app, API, software flaws)
- P: Phishing (social engineering, credential theft)
- I: Insider threat (malicious or negligent insiders)
- D: Denial of Service (DoS, resource exhaustion)
- S: Supply chain risk (third-party, vendor, dependency risks)

Each RAPIDS category scored 0-100 (higher = more risk)

Residual Risk: Risk remaining AFTER controls are applied (0-100 scale)
- 0-10: ACCEPT (low risk, acceptable)
- 10-20: MONITOR (medium risk, watch closely)
- 20+: MITIGATE (high risk, action required)

MITRE Technique: Specific adversary behavior from MITRE ATT&CK framework
- Format: T#### or T####.### (e.g., T1190 = Exploit Public-Facing Application)
- Total: 703 techniques in MITRE ATT&CK v15

Prevention + DIR Framework: Defense-in-Depth strategy
- Prevention (40%): Stop attacks before they start (MFA, WAF, Input Validation)
- Detect (30%): Identify attacks in progress (Logging, SIEM, IDS)
- Isolate (20%): Contain breaches (Network Segmentation, Firewall)
- Respond (10%): Recover from incidents (Backup, Incident Response)

============================================================
SCORING RUBRIC (Security Architect) - 100 Points
============================================================

TIER 1: CRITICAL ARTIFACTS (80 points) - from ground_truth.json

A. Threat Model Completeness (30 points)
   - All entry points identified (8 pts)
   - All data flows mapped (7 pts)
   - Architecture-specific threats considered (8 pts)
   - Trust boundaries clearly defined (7 pts)

B. Control Appropriateness (25 points)
   - Controls match architecture complexity (8 pts)
   - Controls aligned with data sensitivity (9 pts)
   - Controls feasible for architecture type (8 pts)

C. Defense-in-Depth (15 points)
   - Multiple control layers per path (8 pts)
   - No single points of failure unmitigated (7 pts)

D. RAPIDS Alignment (10 points)
   - All 6 RAPIDS categories addressed (5 pts)
   - Controls prioritized by risk score (5 pts)

TIER 2: IMPORTANT ARTIFACTS (20 points) - from report files

E. Diagram Completeness (10 points)
   - All controls visualized in after.mmd (7 pts) **CRITICAL CHECK**
   - Diagram is clear and readable (3 pts)

F. Report Quality (10 points)
   - Technical report has sufficient detail (4 pts)
   - Executive summary is business-friendly (3 pts)
   - Action plan is realistic and phased (3 pts)

**CRITICAL: after.mmd Validation**
Count "NEW_*" nodes in after.mmd and compare with control_recommendations count.
If mismatch (±2 tolerance), flag as HIGH severity gap in diagram_completeness.

SCORING BANDS:
- 90-100: EXCELLENT - Architecture-aware recommendations
- 80-89: GOOD - Minor context improvements possible
- 70-79: FAIR - Some architectural mismatches
- <70: POOR - Significant architectural gaps

============================================================
YOUR ROLE
============================================================

As a Security Architect, focus on:
1. Design quality - Do recommendations fit the architecture?
2. Completeness - Are all entry points and data flows considered?
3. Context - Are controls appropriate for this specific system?
4. Feasibility - Can these controls actually be implemented here?

THINK LIKE AN ARCHITECT:
- "Would I recommend this to a client?"
- "Does this address the actual risks in THIS architecture?"
- "Are we over-engineering or under-protecting?"
- "Will this design withstand a real attack?"

OUTPUT REQUIREMENTS:
- Provide scores for each rubric category
- Identify specific gaps (not vague statements)
- Recommend actionable improvements
- Cite affected components by name
- Estimate impact of improvements

Be critical but constructive. Your goal is to improve the assessment quality.
"""


# ============================================================================
# ENHANCED ARCHITECT CRITIC (Phase 3D v3.0 - Validation-Only)
# ============================================================================

class EnhancedArchitectCritic:
    """
    Architect Critic - VALIDATION-ONLY Mode (Phase 3D)

    Validates the quality of threat assessments generated by deterministic analysis.
    Does NOT generate new threats or controls - only validates existing analysis.

    Contract:
    - Input: ArtifactSet (10 artifacts from deterministic analysis)
    - Output: CritiqueScore (validation gaps + confidence adjustment)
    - Confidence: -0% (excellent) to -10% (major gaps)
    - Prerequisites: All 10 artifacts must exist (enforced by caller)

    Usage:
        architect = EnhancedArchitectCritic()
        score = architect.critique(artifacts)
        confidence_adjustment = -0.10 if score.score < 70 else 0.0
    """

    def __init__(self, model: Optional[str] = None):
        self.agent = create_architect_agent(model)
        self.model = model
        logger.info("EnhancedArchitectCritic initialized (validation-only mode)")

    def critique(self, artifacts: ArtifactSet) -> 'CritiqueScore':
        """
        Validate threat assessment quality (VALIDATION-ONLY).

        Does NOT generate new recommendations - validates existing analysis quality.

        Prerequisites (enforced by MoEOrchestrator):
        - ground_truth.json exists
        - All 10 artifacts present in ArtifactSet

        Args:
            artifacts: ArtifactSet with 10 artifacts from deterministic analysis

        Returns:
            CritiqueScore with:
            - score: 0-100 (validation quality)
            - gaps: List of validation issues found
            - strengths: What the analysis did well
            - improvement_roadmap: How to fix validation gaps

        Raises:
            ValueError: If artifacts incomplete (should not happen if MoE used correctly)
        """
        from chatbot.modules.agent_framework import CritiqueScore

        # Validate prerequisites (defensive check - MoE should ensure this)
        completeness = artifacts.completeness['overall']
        if completeness['present'] < 10:
            logger.warning(
                f"Architect: Incomplete artifacts ({completeness['present']}/10). "
                f"Quality may be degraded."
            )

        logger.info(f"Architect: Validating threat model quality ({completeness['present']}/10 artifacts)")

        # Format prompt with all 10 artifacts
        prompt = self._format_prompt(artifacts)

        # Use base agent to generate critique
        # Note: We pass a minimal ground_truth dict for compatibility
        # The real critique happens via the enhanced prompt
        minimal_gt = {
            "architecture": "enhanced_critique",
            "expected_attack_paths": artifacts.tier1_critical["artifact_1_attack_paths"]["paths"],
            "control_recommendations": artifacts.tier1_critical["artifact_2_controls"]["controls"]
        }

        # Override the agent's prompt formatter
        original_formatter = self.agent._format_prompt
        self.agent._format_prompt = lambda gt: prompt

        try:
            score = self.agent.critique(minimal_gt)
            return score
        finally:
            # Restore original formatter
            self.agent._format_prompt = original_formatter

    def _format_prompt(self, artifacts: ArtifactSet) -> str:
        """
        Format comprehensive prompt with all 10 artifacts.
        """
        tier1 = artifacts.tier1_critical
        tier2 = artifacts.tier2_important
        indexes = artifacts.indexes

        # Extract key counts
        path_count = tier1["artifact_1_attack_paths"]["count"]
        control_count = tier1["artifact_2_controls"]["count"]
        after_mmd_controls = indexes["after_mmd_controls"]

        # Check after.mmd completeness (CRITICAL)
        control_gap = abs(after_mmd_controls - control_count)
        control_status = "✅ COMPLETE" if control_gap <= 2 else f"❌ GAP: {control_gap} controls missing"

        prompt = f"""RESPONSE FORMAT: You must reply with a single ```json code block. No prose before or after it. Your entire response is the JSON object described at the bottom of this prompt.

{'='*70}
You are reviewing a threat assessment with 10 artifacts (5 critical + 5 important).
{'='*70}
TIER 1: CRITICAL ARTIFACTS (80 points weight)
{'='*70}

ARTIFACT 1: ATTACK PATHS ({path_count} paths)
{self._format_attack_paths(tier1["artifact_1_attack_paths"])}

ARTIFACT 2: CONTROL RECOMMENDATIONS ({control_count} controls)
{self._format_controls(tier1["artifact_2_controls"])}

SSP POLICY CONTEXT (Singapore Government ICT&SS Baseline):
{self._format_ssp_context(tier1["artifact_2_controls"])}

ARTIFACT 3: RESIDUAL RISK (BEFORE → AFTER)
{self._format_residual_risk(tier1["artifact_3_residual_risk"])}

ARTIFACT 4: VALIDATION RESULTS
{self._format_validation(tier1["artifact_4_validation"])}

ARTIFACT 5: RAPIDS ASSESSMENT (6 threat categories)
{self._format_rapids(tier1["artifact_5_rapids"])}

{self._format_story_context(indexes)}

{'='*70}
TIER 2: IMPORTANT ARTIFACTS (20 points weight)
{'='*70}

ARTIFACT 6: ORIGINAL ARCHITECTURE (before.mmd)
{self._format_diagram(tier2.get("artifact_6_before_mmd"), "Before")}

ARTIFACT 7: IMPROVED ARCHITECTURE (after.mmd) **CRITICAL VALIDATION**
{self._format_diagram(tier2.get("artifact_7_after_mmd"), "After")}

**CRITICAL CHECK - after.mmd Completeness:**
- Expected controls: {control_count}
- Controls in after.mmd: {after_mmd_controls} NEW_* nodes
- Status: {control_status}

{'→ ' if control_gap > 2 else ''}{'FLAG THIS AS HIGH SEVERITY GAP if mismatch > 2' if control_gap > 2 else ''}

ARTIFACT 8: TECHNICAL REPORT
{self._format_report(tier2.get("artifact_8_technical_report"), "Technical", max_lines=30)}

ARTIFACT 9: EXECUTIVE SUMMARY
{self._format_report(tier2.get("artifact_9_executive_summary"), "Executive", max_lines=20)}

ARTIFACT 10: ACTION PLAN
{self._format_report(tier2.get("artifact_10_action_plan"), "Action Plan", max_lines=20)}

{'='*70}
YOUR CRITIQUE
{'='*70}

Score each category (100 points total):
- Tier 1 (Critical): 80 points (Artifacts 1-5)
- Tier 2 (Important): 20 points (Artifacts 6-10)

Focus on:
1. **after.mmd completeness** (most critical Tier 2 check)
2. Attack path completeness and realism
3. Control appropriateness for architecture
4. Defense-in-depth coverage
5. RAPIDS threat alignment
6. **SSP policy alignment** — are L0 cardinal controls present? Are any L0 gaps present that would require HQ approval to defer?
7. **User journey alignment** — do the recommended controls match the dominant flow types above? Attacker-only paths (no user baseline) should receive anomaly detection or network segmentation controls, since behavioral baselines cannot flag them.

{'='*70}
OUTPUT FORMAT (JSON REQUIRED)
{'='*70}

You MUST respond with valid JSON in this exact format:

```json
{{
  "score": 85,
  "max_score": 100,
  "rating": "GOOD",
  "reasoning": "1-2 sentences naming the single most important structural finding and its direct consequence. State facts — name the specific component or path. Do not use evaluative adjectives like 'excellent' or 'impressive'. Do not reference tool names, frameworks, or country context unless directly relevant to the finding.",
  "breakdown": {{
    "threat_completeness": {{"score": 25, "max": 30, "reasoning": "..."}},
    "control_appropriateness": {{"score": 22, "max": 25, "reasoning": "..."}},
    "defense_in_depth": {{"score": 13, "max": 15, "reasoning": "..."}},
    "rapids_alignment": {{"score": 8, "max": 10, "reasoning": "..."}},
    "diagram_completeness": {{"score": 8, "max": 10, "reasoning": "..."}},
    "report_quality": {{"score": 9, "max": 10, "reasoning": "..."}}
  }},
  "gaps": [
    {{
      "category": "diagram_completeness",
      "severity": "HIGH",
      "description": "<ONE sentence: the fact. Name the specific artifact, control, or path. No explanations or breakdowns.>",
      "recommendation": "<ONE sentence: the action to take. No sub-steps.>",
      "affected_components": ["Artifact 7 (after.mmd)"]
    }}
  ],
  "strengths": [
    "All 10 artifacts present",
    "Comprehensive control coverage"
  ],
  "improvement_roadmap": [
    {{
      "priority": 1,
      "action": "<ONE sentence: what to change.>",
      "category": "diagram_completeness",
      "points_gained": 2,
      "effort": "LOW",
      "verification_method": "<ONE concrete check — a grep, a count, or a single measurable outcome. No multi-step procedures. Example: `grep -c NEW_ after.mmd` should equal {control_count}>",
      "expected_outcome": "<ONE sentence: the measurable result.>"
    }}
  ]
}}
```

**OUTPUT TONE RULES:**
- gaps[].description: ONE sentence. State the fact. Name the artifact/control/path. No taxonomy breakdowns, no "likely counts", no nested explanations.
- gaps[].recommendation: ONE actionable instruction. What to do. No sub-steps or option lists inside the field.
- improvement_roadmap[].action: ONE sentence stating what to change.
- improvement_roadmap[].verification_method: ONE concrete check — a command or a single measurable count. Not a procedure.
  GOOD: "`grep -c NEW_ after.mmd` should equal {control_count}"
  BAD: "Parse after.mmd, categorize nodes into (1) pre-existing... (2) NEW_*... (3) labels..."
- Write for a practitioner who executes this, not a committee that debates it.

**CRITICAL REQUIREMENTS:**
1. Response MUST be valid JSON (use ```json code block)
2. Include ALL 6 rubric categories in breakdown
3. gaps array must have severity (HIGH/MEDIUM/LOW)
4. improvement_roadmap must include verification_method for Tester
5. Be specific: cite artifact numbers, control names, path IDs
6. **TECHNIQUE IDs ONLY FROM ARTIFACTS** — when mentioning MITRE technique IDs (T####.###), only reference IDs that appear verbatim in the artifact data above. Never invent, guess, or describe technique IDs that are not present in the input artifacts. If you want to suggest additional coverage, say "add coverage for [threat type]" without fabricating a technique ID.
"""

        return prompt

    def _format_attack_paths(self, artifact: Dict) -> str:
        """Format attack paths artifact."""
        paths = artifact["paths"]
        lines = []
        for idx, path in enumerate(paths):
            path_name = path.get("path_name", f"Path #{idx+1}")
            techniques = path.get("techniques", [])
            hop_count = path.get("hop_count", len(path.get("path", [])))
            criticality = path.get("criticality", "UNKNOWN")

            lines.append(f"  Path #{idx+1}: {path_name}")
            lines.append(f"    Hops: {hop_count} | Criticality: {criticality}")
            lines.append(f"    Techniques: {', '.join(techniques)}")

        return "\n".join(lines)

    def _format_controls(self, artifact: Dict) -> str:
        """Format controls artifact."""
        controls = artifact["controls"]
        lines = []
        for idx, control in enumerate(controls[:10]):  # Show first 10
            name = control.get("control", "Unknown")
            priority = control.get("priority", "unknown")
            score = control.get("score", 0)
            paths = control.get("attack_paths", [])
            ssp_ctx = control.get("ssp_context")
            ssp_note = ""
            if ssp_ctx and ssp_ctx.get("primary"):
                p = ssp_ctx["primary"]
                ssp_note = f" [SSP: {ssp_ctx['label']} L{p['level']}]"

            lines.append(f"  {idx+1}. {name.upper()} [{priority}] (score: {score:.1f}){ssp_note}")
            lines.append(f"     Affects paths: {paths}")

        if len(controls) > 10:
            lines.append(f"  ... +{len(controls) - 10} more controls")

        return "\n".join(lines)

    def _format_ssp_context(self, artifact: Dict) -> str:
        """Format SSP policy context summary for the critic prompt."""
        controls = artifact["controls"]
        ssp_recs = [c for c in controls if c.get("ssp_context") and c["ssp_context"].get("primary")]
        if not ssp_recs:
            return "  (No SSP enrichment data available)"

        profile = ssp_recs[0]["ssp_context"].get("profile", "unknown").replace("_", " ").title()
        lines = [f"  Profile: {profile}"]
        lines.append("  L0=Cardinal(HQ approval if skipped) | L1=Basic Hygiene(SC risk acceptance) | L2=Best Practice(risk-owner acceptance)")
        lines.append("")
        l0 = [c for c in ssp_recs if c["ssp_context"]["primary"]["level"] == 0]
        l1 = [c for c in ssp_recs if c["ssp_context"]["primary"]["level"] == 1]
        l2 = [c for c in ssp_recs if c["ssp_context"]["primary"]["level"] == 2]
        if l0:
            lines.append(f"  L0 Cardinal ({len(l0)}): " + ", ".join(f"{c['ssp_context']['label']} {c['control'].upper()}" for c in l0[:5]))
        if l1:
            lines.append(f"  L1 Hygiene  ({len(l1)}): " + ", ".join(f"{c['ssp_context']['label']} {c['control'].upper()}" for c in l1[:5]))
        if l2:
            lines.append(f"  L2 Practice ({len(l2)}): " + ", ".join(f"{c['ssp_context']['label']} {c['control'].upper()}" for c in l2[:5]))
        return "\n".join(lines)

    def _format_residual_risk(self, artifact: Dict) -> str:
        """Format residual risk artifact."""
        before = artifact["before"]
        after = artifact["after"]
        reduction = artifact["reduction"]

        return f"""  Before: {before['score']}/100 (Defensibility: {before.get('defensibility', 'N/A')})
  After:  {after['score']}/100 (Defensibility: {after.get('defensibility', 'N/A')})
  Reduction: {reduction['absolute']} points ({reduction['percentage']:.1f}%)"""

    def _format_validation(self, artifact: Dict) -> str:
        """Format validation artifact."""
        overall = "✅ VALID" if artifact["overall_valid"] else "❌ INVALID"
        confidence = artifact["confidence_baseline"]
        issues = artifact["issues"]

        return f"""  Overall: {overall}
  Confidence: {confidence:.1%}
  Issues found: {len(issues)}"""

    def _format_story_context(self, indexes: Dict) -> str:
        """Format StoryCaster user journey context for architect review."""
        si = indexes.get("story_index")
        if not si:
            return ""

        lines = ["USER JOURNEY CONTEXT (StoryCaster):"]
        lines.append(f"  {si['summary']}")

        by_type = si.get("by_type", {})
        if by_type:
            dist = ", ".join(f"{t}: {c}" for t, c in sorted(by_type.items(), key=lambda x: -x[1]))
            lines.append(f"  Flow distribution: {dist}")

        attacker_only = si.get("attacker_only", [])
        if attacker_only:
            lines.append(f"  ⚠ Attacker-only paths ({len(attacker_only)}) — no user baseline:")
            for j in attacker_only:
                path_str = " → ".join(j.get("path_labels", j.get("path", [])))
                lines.append(f"    · {j.get('attack_path_id', '?')}: {path_str}")

        high_risk = si.get("high_risk", [])
        if high_risk:
            lines.append(f"  High-risk corroborated journeys ({len(high_risk)}):")
            for j in high_risk[:3]:
                lines.append(
                    f"    · {j.get('story_id','?')} [{j.get('user_role','?')}] "
                    f"{j.get('actor_label','?')} → {j.get('resource_label','?')} "
                    f"({', '.join(j.get('threat_relevance',[]))})"
                )

        return "\n".join(lines)

    def _format_rapids(self, artifact: Dict) -> str:
        """Format RAPIDS artifact."""
        categories = artifact["categories"]
        lines = []
        for name, data in categories.items():
            risk = data.get("risk", 0)
            defensibility = data.get("defensibility", 0)
            lines.append(f"  {name.upper()}: Risk={risk}/100, Defensibility={defensibility}%")

        return "\n".join(lines)

    def _format_diagram(self, content: Optional[str], label: str) -> str:
        """Format diagram artifact."""
        if not content:
            return f"  ❌ {label} diagram missing"

        # Count nodes
        node_count = content.count("[") + content.count("((") + content.count("[(")
        new_control_count = content.count("NEW_")

        return f"""  ✅ {label} diagram present
  Nodes: ~{node_count} | NEW controls: {new_control_count}
  (First 3 lines: {content.split(chr(10))[:3]})"""

    def _format_report(self, content: Optional[str], label: str, max_lines: int = 20) -> str:
        """Format report artifact."""
        if not content:
            return f"  ❌ {label} report missing"

        lines = content.split("\n")
        preview = "\n".join(lines[:max_lines])
        total_lines = len(lines)

        return f"""  ✅ {label} report present ({total_lines} lines)
  Preview (first {max_lines} lines):
{preview}
  ... ({total_lines - max_lines} more lines)"""


# ============================================================================
# ARCHITECT AGENT FACTORY
# ============================================================================

def create_architect_agent(model: Optional[str] = None) -> CriticAgent:
    """
    Create configured Architect critic agent.

    Args:
        model: LLM model to use (via LiteLLM). If None, uses .env configuration.
               .env settings: LLM_PROVIDER, OPENROUTER_MODEL, BEDROCK_MODEL, etc.

    Returns: Configured CriticAgent
    """
    tools = [
        AgentTool(
            name="search_control_context",
            description="Search for control best practices in given architecture context",
            function=search_control_context,
            parameters={
                "type": "object",
                "properties": {
                    "control_name": {
                        "type": "string",
                        "description": "Control to research (e.g., WAF, MFA, Rate Limiting)"
                    },
                    "architecture_type": {
                        "type": "string",
                        "description": "Architecture type (web_app, ai_system, iot, generic)"
                    }
                },
                "required": ["control_name", "architecture_type"]
            }
        ),
        AgentTool(
            name="check_architecture_type",
            description="Identify architecture type from component names",
            function=check_architecture_type,
            parameters={
                "type": "object",
                "properties": {
                    "components": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of component names from architecture"
                    }
                },
                "required": ["components"]
            }
        )
    ]

    agent = CriticAgent(
        role="Security Architect",
        rubric=ARCHITECT_RUBRIC,
        system_prompt=ARCHITECT_SYSTEM_PROMPT,
        tools=tools,
        model=model
    )

    logger.info("Created Architect critic agent")
    return agent


# ============================================================================
# CLI TEST INTERFACE (for MVP1 testing)
# ============================================================================

if __name__ == "__main__":
    import sys
    import json
    from pathlib import Path

    # Simple CLI for testing
    if len(sys.argv) < 2:
        print("Usage: python -m chatbot.modules.architect_critic <architecture_name>")
        print("Example: python -m chatbot.modules.architect_critic 10_complex_enterprise")
        sys.exit(1)

    arch_name = sys.argv[1]
    ground_truth_path = Path(f"report/{arch_name}/ground_truth.json")

    if not ground_truth_path.exists():
        print(f"Error: Ground truth not found at {ground_truth_path}")
        print("Run: python3 -m chatbot.main --gen-arch-truth <architecture.mmd> first")
        sys.exit(1)

    # Load ground truth
    with open(ground_truth_path) as f:
        ground_truth = json.load(f)

    # Create agent and run critique
    print(f"\n{'='*70}")
    print(f"ARCHITECT CRITIQUE: {arch_name}")
    print(f"{'='*70}\n")

    agent = create_architect_agent()
    score = agent.critique(ground_truth)

    # Print results
    print(f"\n{'='*70}")
    print(f"RESULTS")
    print(f"{'='*70}\n")
    print(f"Score: {score.score}/{score.max_score} ({score.rating})")
    print(f"\nBreakdown:")
    for category, data in score.breakdown.items():
        print(f"  {category}: {data.get('score', 0)}/{data.get('max', 0)}")

    print(f"\nGaps Found: {len(score.gaps)}")
    for i, gap in enumerate(score.gaps, 1):
        print(f"\n{i}. [{gap.get('severity', 'UNKNOWN')}] {gap.get('category', 'Unknown')}")
        print(f"   {gap.get('description', 'No description')}")
        print(f"   Recommendation: {gap.get('recommendation', 'None')}")

    print(f"\nStrengths: {len(score.strengths)}")
    for i, strength in enumerate(score.strengths, 1):
        print(f"  {i}. {strength}")

    print(f"\n{'='*70}")
    print(f"IMPROVEMENT ROADMAP (How to increase score)")
    print(f"{'='*70}")
    if score.improvement_roadmap:
        total_gain = sum(item.get('points_gained', 0) for item in score.improvement_roadmap)
        target_score = min(score.score + total_gain, 100)

        # Check if normalized
        has_original = any('original_points' in item for item in score.improvement_roadmap)
        if has_original:
            original_total = sum(item.get('original_points', item.get('points_gained', 0))
                               for item in score.improvement_roadmap)
            print(f"Current: {score.score}/100 → Target: {target_score}/100 (+{total_gain} points)")
            print(f"Note: Points normalized from {original_total} → {total_gain} (realistic target)")
        else:
            print(f"Current: {score.score}/100 → Target: {target_score}/100 (+{total_gain} points)")

        # Determine rating at target
        if target_score >= 90:
            target_rating = "EXCELLENT"
        elif target_score >= 80:
            target_rating = "GOOD"
        elif target_score >= 70:
            target_rating = "FAIR"
        else:
            target_rating = "POOR"
        print(f"Target Rating: {target_rating}\n")

        for item in score.improvement_roadmap:
            priority = item.get('priority', '?')
            action = item.get('action', 'N/A')
            points = item.get('points_gained', 0)
            effort = item.get('effort', 'N/A')
            verification = item.get('verification_method', 'N/A')

            # Show if normalized
            if 'original_points' in item:
                original = item['original_points']
                print(f"Priority {priority}: {action}")
                print(f"  Points gained: +{points} (normalized from +{original}) | Effort: {effort}")
            else:
                print(f"Priority {priority}: {action}")
                print(f"  Points gained: +{points} | Effort: {effort}")

            print(f"  Verification: {verification}")
            print()
    else:
        print("(No roadmap provided)")

    # Save results
    output_path = Path(f"report/{arch_name}/04_architect_critique.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w') as f:
        json.dump(score.to_dict(), f, indent=2)

    print(f"\n{'='*70}")
    print(f"Saved to: {output_path}")
    print(f"{'='*70}\n")


# CriticRegistry self-registration
try:
    from chatbot.harness.registry import _DEFAULT_REGISTRY, CriticDescriptor
    _DEFAULT_REGISTRY.register(CriticDescriptor(
        name="architect", cls=EnhancedArchitectCritic,
        governance_tier="standard", model_key="architect",
    ))
except Exception:
    pass
