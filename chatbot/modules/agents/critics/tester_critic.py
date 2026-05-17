"""
Tester Critic Agent for Phase 3C

Role: Quality Assurance Tester validating threat assessment quality

Focus: Internal consistency, validation checks, coverage metrics, MITRE correctness

Approach: Prompt-based (no tool calling) with embedded MITRE data
- LLM receives comprehensive MITRE reference in prompt
- Validates technique-mitigation mappings
- Scores control effectiveness
- Cross-checks rationales with inventory

Confidence Target: 75-80% (without tools, using embedded data)

VERSION: 1.0 - Prompt-based implementation (MVP)
"""

import json
import logging
from typing import Dict, List, Optional

from chatbot.modules.agent_framework import CriticAgent
from chatbot.modules.artifact_extractor import ArtifactSet
from chatbot.modules.mitre import MitreHelper

logger = logging.getLogger(__name__)


# ============================================================================
# TESTER RUBRIC
# ============================================================================

TESTER_RUBRIC = {
    # TIER 1: Validation Checks (40 points)
    "validation_checks": {
        "max": 40,
        "tier": 1,
        "criteria": {
            "ground_truth_valid": {"points": 10, "description": "Ground truth validation passed"},
            "mitre_mappings_valid": {"points": 10, "description": "Control-technique mappings valid per MITRE"},
            "risk_score_consistent": {"points": 10, "description": "Risk scores mathematically consistent"},
            "technique_coverage": {"points": 10, "description": "Technique coverage adequate"}
        }
    },

    # TIER 2: Coverage Metrics (30 points)
    "coverage_metrics": {
        "max": 30,
        "tier": 1,
        "criteria": {
            "rapids_complete": {"points": 10, "description": "All 6 RAPIDS categories assessed"},
            "technique_ratio": {"points": 10, "description": "Technique-to-risk ratio appropriate"},
            "control_coverage": {"points": 10, "description": "Control-to-threat coverage sufficient"}
        }
    },

    # TIER 3: Internal Consistency (20 points)
    "internal_consistency": {
        "max": 20,
        "tier": 1,
        "criteria": {
            "rationale_matches": {"points": 10, "description": "Control rationales match inventory"},
            "priority_aligned": {"points": 10, "description": "Priorities aligned to risk scores"}
        }
    },

    # TIER 4: Architect Roadmap Validation (10 points)
    "roadmap_validation": {
        "max": 10,
        "tier": 1,
        "criteria": {
            "addresses_gaps": {"points": 5, "description": "Roadmap items address real gaps"},
            "realistic_claims": {"points": 5, "description": "Improvement claims are realistic"}
        }
    }
}


# ============================================================================
# TESTER SYSTEM PROMPT
# ============================================================================

TESTER_SYSTEM_PROMPT = """You are a Security Tester validating threat assessment quality.

Your role: Verify that security assessments are:
1. Technically correct (valid MITRE mappings)
2. Internally consistent (rationales match reality)
3. Appropriately scoped (coverage matches threats)
4. Realistically improved (roadmap is achievable)

IMPORTANT: You have comprehensive MITRE ATT&CK data in your prompt.
Use it to validate technique-mitigation mappings without hallucinating.

SCORING RUBRIC (100 points):

A. VALIDATION CHECKS (40 points)
   - Ground truth validation passed (10 pts)
   - MITRE mappings valid (10 pts) ← Check against provided MITRE reference
   - Risk score consistency (10 pts)
   - Technique coverage adequate (10 pts)

B. COVERAGE METRICS (30 points)
   - RAPIDS completeness (6/6 categories) (10 pts)
   - Technique-to-risk ratio appropriate (10 pts)
   - Control-to-threat coverage sufficient (10 pts)

C. INTERNAL CONSISTENCY (20 points)
   - Control rationales match inventory (10 pts)
   - Priorities aligned to risk scores (10 pts)

D. ARCHITECT ROADMAP VALIDATION (10 points)
   - Roadmap items address real gaps (5 pts)
   - Improvement claims are realistic (5 pts)

VALIDATION APPROACH:

For MITRE mappings:
1. Check control's claimed mitigations (e.g., M1032)
2. Check control's claimed techniques (e.g., T1078)
3. Verify: Is M1032 in T1078's mitigation list? (use provided MITRE reference)
4. Calculate coverage: How many techniques are actually mitigated?

For internal consistency:
1. Check if rationale mentions controls
2. Verify controls exist in inventory
3. Flag contradictions (e.g., "backup recommended" but backup in controls_missing)

For coverage:
1. High-risk threats (risk >= 70) should have multiple controls
2. Critical paths should have defense-in-depth (3+ controls)
3. RAPIDS categories with high risk should have corresponding controls

OUTPUT FORMAT: JSON

Return valid JSON with this structure:
```json
{
  "score": 75,
  "max_score": 100,
  "rating": "FAIR",
  "breakdown": {
    "validation_checks": {"score": 35, "max": 40, "reasoning": "..."},
    "coverage_metrics": {"score": 20, "max": 30, "reasoning": "..."},
    "internal_consistency": {"score": 15, "max": 20, "reasoning": "..."},
    "roadmap_validation": {"score": 5, "max": 10, "reasoning": "..."}
  },
  "gaps": [
    {
      "category": "validation_checks",
      "severity": "HIGH",
      "description": "Control X claims to mitigate T1234 but M1234 not in T1234's mitigations",
      "affected_components": ["Control X"],
      "recommendation": "Remove T1234 from Control X or verify MITRE mapping"
    }
  ],
  "strengths": [
    "All 6 RAPIDS categories assessed",
    "Validation checks passed"
  ],
  "improvement_roadmap": [
    {
      "priority": 1,
      "action": "Fix invalid MITRE mapping for Control X",
      "category": "validation_checks",
      "points_gained": 5,
      "effort": "LOW",
      "verification_method": "Re-check T1234's mitigations in MITRE ATT&CK",
      "expected_outcome": "Control X accurately mapped"
    }
  ]
}
```

Be specific: Cite control names, technique IDs, and use MITRE data provided.
Be critical: Flag issues even if assessment looks "good enough".
Be constructive: Provide actionable recommendations.
"""


# ============================================================================
# PROMPT BUILDERS
# ============================================================================

def build_mitre_reference(techniques: List[str], mitre: MitreHelper) -> Dict:
    """
    Build MITRE reference for techniques.

    Args:
        techniques: List of technique IDs (e.g., ["T1078", "T1110"])
        mitre: MitreHelper instance

    Returns:
        Dict mapping technique_id to {name, mitigations}
    """
    reference = {}

    for tech_id in set(techniques):
        tech = mitre.find_technique(tech_id)
        if not tech:
            logger.warning(f"Technique {tech_id} not found in MITRE")
            continue

        # Get mitigations
        tech_internal_id = tech.get('id')
        mitigations = mitre.get_technique_mitigations(tech_internal_id)

        reference[tech_id] = {
            "name": tech.get("name", "Unknown"),
            "description": tech.get("description", "")[:200],  # Truncate
            "mitigations": [m["mitigation_id"] for m in mitigations]
        }

    return reference


def format_mitre_reference(reference: Dict) -> str:
    """Format MITRE reference for prompt."""
    lines = []

    for tech_id, data in reference.items():
        mits = ", ".join(data["mitigations"]) if data["mitigations"] else "None"
        lines.append(f"  {tech_id} ({data['name']})")
        lines.append(f"    Mitigations: {mits}")

    return "\n".join(lines)


def format_controls_summary(controls: List[Dict]) -> str:
    """
    Format controls for prompt (HYBRID APPROACH).

    Shows both:
    - Defense-in-depth: All mitigations the control implements
    - Validation: Per-technique coverage map (which mitigation addresses which technique)
    """
    lines = []

    for idx, control in enumerate(controls[:15], 1):  # Limit to 15 for token economy
        name = control.get("control", "Unknown")
        mits = control.get("mitigations", [])
        techs = control.get("techniques", [])
        priority = control.get("priority", "unknown")
        score = control.get("score", 0)

        lines.append(f"  {idx}. {name.upper()} [{priority}] (score: {score:.1f})")

        # Check for coverage note (explains why no techniques)
        coverage_note = control.get("coverage_note")
        if coverage_note:
            lines.append(f"     Note: {coverage_note}")
            lines.append(f"     No MITRE validation needed (preventive control, not runtime mitigation)")
            continue  # Skip to next control

        lines.append(f"     Implements mitigations (defense-in-depth): {', '.join(mits) if mits else '(none)'}")

        # HYBRID: Show per-technique coverage if available
        technique_coverage = control.get("technique_coverage", {})
        if len(techs) > 0 and technique_coverage is not None:
            lines.append(f"     Per-technique mappings (validate these against MITRE):")
            # Show first 5 techniques with their valid mitigations
            for tech_id in list(techs)[:5]:
                valid_mits = technique_coverage.get(tech_id, [])
                if valid_mits:
                    lines.append(f"       • {tech_id} ← mitigated by: {', '.join(valid_mits)}")
                else:
                    lines.append(f"       • {tech_id} ← (NO valid mitigations from this control)")
            if len(techs) > 5:
                lines.append(f"       ... +{len(techs) - 5} more techniques")
            lines.append(f"     IMPORTANT: Only validate the per-technique mappings above, NOT the full mitigation list")
        elif len(techs) == 0:
            lines.append(f"     No techniques mapped (preventive/detective control)")
        else:
            # Fallback: Old format (claims all mitigations for all techniques)
            lines.append(f"     Claims ALL mitigations apply to ALL techniques: {', '.join(techs)}")
            lines.append(f"     WARNING: Old format - validate each mitigation against each technique")

    if len(controls) > 15:
        lines.append(f"  ... +{len(controls) - 15} more controls")

    return "\n".join(lines)


def format_attack_paths_summary(attack_paths: Dict) -> str:
    """Format attack paths for prompt."""
    paths = attack_paths["paths"]
    lines = []

    for idx, path in enumerate(paths[:5], 1):  # Limit to 5
        path_name = path.get("path_name", f"Path #{idx}")
        techniques = path.get("techniques", [])
        criticality = path.get("criticality", "UNKNOWN")

        lines.append(f"  Path {idx}: {path_name} [{criticality}]")
        lines.append(f"    Techniques ({len(techniques)}): {', '.join(techniques[:10])}")

    if len(paths) > 5:
        lines.append(f"  ... +{len(paths) - 5} more paths")

    return "\n".join(lines)


def format_validation_report(validation: Dict) -> str:
    """Format validation report summary."""
    overall = "✅ VALID" if validation["overall_valid"] else "❌ INVALID"
    confidence = validation.get("confidence_baseline", 0)
    issues = validation.get("issues", [])

    lines = [
        f"  Overall: {overall}",
        f"  Confidence: {confidence:.1%}",
        f"  Issues: {len(issues)}"
    ]

    if issues:
        lines.append("  Issue details:")
        for issue in issues[:3]:
            lines.append(f"    - {issue}")
        if len(issues) > 3:
            lines.append(f"    ... +{len(issues) - 3} more issues")

    return "\n".join(lines)


def format_architect_roadmap(roadmap: List[Dict]) -> str:
    """Format architect roadmap for validation."""
    if not roadmap:
        return "  (No roadmap provided)"

    lines = []
    for item in roadmap[:5]:
        priority = item.get("priority", "?")
        action = item.get("action", "N/A")
        points = item.get("points_gained", 0)
        verification = item.get("verification_method", "N/A")

        lines.append(f"  Priority {priority}: {action} (+{points} pts)")
        lines.append(f"    Verification: {verification}")

    if len(roadmap) > 5:
        lines.append(f"  ... +{len(roadmap) - 5} more items")

    return "\n".join(lines)


def create_tester_prompt(
    artifacts: ArtifactSet,
    architect_critique: Optional['CritiqueScore'] = None
) -> str:
    """
    Create comprehensive Tester prompt with embedded MITRE data.

    Args:
        artifacts: ArtifactSet from artifact_extractor
        architect_critique: Optional Architect critique to validate

    Returns:
        Prompt string with all data embedded
    """
    tier1 = artifacts.tier1_critical
    tier2 = artifacts.tier2_important

    # Extract all techniques
    all_techniques = []
    for path in tier1["artifact_1_attack_paths"]["paths"]:
        all_techniques.extend(path.get("techniques", []))

    # Build MITRE reference
    mitre = MitreHelper(use_local=True)
    mitre_reference = build_mitre_reference(all_techniques, mitre)

    # Extract key data
    controls = tier1["artifact_2_controls"]["controls"]
    attack_paths = tier1["artifact_1_attack_paths"]
    residual_risk = tier1["artifact_3_residual_risk"]
    validation = tier1["artifact_4_validation"]
    rapids = tier1["artifact_5_rapids"]

    prompt = f"""You are validating a threat assessment with {artifacts.completeness['overall']['present']}/10 artifacts.

{'='*70}
TIER 1: CRITICAL ARTIFACTS
{'='*70}

ATTACK PATHS ({attack_paths['count']} paths):
{format_attack_paths_summary(attack_paths)}

CONTROLS ({len(controls)} controls):
{format_controls_summary(controls)}

RESIDUAL RISK (BEFORE → AFTER):
  Before: {residual_risk['before']['score']}/100 (Defensibility: {residual_risk['before'].get('defensibility', 'N/A')})
  After:  {residual_risk['after']['score']}/100 (Defensibility: {residual_risk['after'].get('defensibility', 'N/A')})
  Reduction: {residual_risk['reduction']['absolute']} points ({residual_risk['reduction']['percentage']:.1f}%)

VALIDATION RESULTS:
{format_validation_report(validation)}

RAPIDS ASSESSMENT (6 categories):
"""

    # Add RAPIDS summary
    for category, data in rapids["categories"].items():
        risk = data.get("risk", 0)
        defensibility = data.get("defensibility", 0)
        prompt += f"  {category.upper()}: Risk={risk}/100, Defensibility={defensibility}%\n"

    prompt += f"""
{'='*70}
MITRE ATT&CK REFERENCE
{'='*70}

Use this reference to validate control-technique mappings.
DO NOT hallucinate - only use what's listed here.

{format_mitre_reference(mitre_reference)}

{'='*70}
TIER 2: IMPORTANT ARTIFACTS
{'='*70}

Diagram Completeness:
  before.mmd: {'✅' if tier2.get('artifact_6_before_mmd') else '❌'}
  after.mmd: {'✅' if tier2.get('artifact_7_after_mmd') else '❌'}
  after.mmd controls: {artifacts.indexes['after_mmd_controls']} NEW_* nodes vs {len(controls)} recommended

Report Quality:
  Technical report: {'✅' if tier2.get('artifact_8_technical_report') else '❌'}
  Executive summary: {'✅' if tier2.get('artifact_9_executive_summary') else '❌'}
  Action plan: {'✅' if tier2.get('artifact_10_action_plan') else '❌'}
"""

    # Add Architect roadmap if provided
    if architect_critique:
        prompt += f"""
{'='*70}
ARCHITECT ROADMAP (to validate)
{'='*70}

Architect Score: {architect_critique.score}/100 ({architect_critique.rating})

Improvement Roadmap:
{format_architect_roadmap(architect_critique.improvement_roadmap)}
"""

    prompt += f"""
{'='*70}
YOUR VALIDATION TASK
{'='*70}

HYBRID VALIDATION APPROACH:
Controls use a defense-in-depth strategy where a single control may implement multiple
MITRE mitigations, but each mitigation only applies to specific techniques per MITRE ATT&CK.

EXAMPLE:
  Control: LEAST PRIVILEGE
  Implements mitigations: [M1016, M1018, M1026, M1042]  ← Defense-in-depth
  Addresses techniques via:
    T1059: M1026, M1042  ← Only these mitigations valid for T1059 per MITRE
    T1190: M1016, M1026  ← M1016 valid for T1190
    T1213: M1018         ← Only M1018 valid for T1213

VALIDATION RULES:
✅ VALID: Control implements M1016 AND it's applied only where MITRE says it's valid (T1190)
❌ INVALID: Control claims M1016 addresses T1059 (M1016 not in T1059's MITRE mitigation list)

**COMMON MISTAKE TO AVOID:**
❌ WRONG: "LEAST PRIVILEGE implements M1016, so it must claim M1016 for all techniques"
✅ RIGHT: "LEAST PRIVILEGE shows T1059 ← M1026, M1042 (NOT M1016), so only validate M1026/M1042 for T1059"

**HOW TO READ THE CONTROL FORMAT:**
```
Control: LEAST PRIVILEGE
  Implements mitigations (defense-in-depth): M1016, M1018, M1026, M1042
  Per-technique mappings (validate these against MITRE):
    • T1059 ← mitigated by: M1026, M1042
    • T1190 ← mitigated by: M1016, M1026
    • T1213 ← mitigated by: M1018
```

WHAT TO VALIDATE:
- T1059: Check if M1026 and M1042 are valid (YES, they are) ✅
- T1190: Check if M1016 and M1026 are valid (YES, they are) ✅
- T1213: Check if M1018 is valid (YES, it is) ✅

WHAT NOT TO DO:
- ❌ DON'T check if M1016 is valid for T1059 (it's not claimed for T1059!)
- ❌ DON'T check if M1018 is valid for T1059 (it's not claimed for T1059!)
- ❌ DON'T assume "Implements M1016" means it claims M1016 for ALL techniques

1. VALIDATE MITRE MAPPINGS (USE HYBRID STRUCTURE - READ CAREFULLY):
   For each control, check:
   a) If control shows "Per-technique mappings (validate these against MITRE)":
      - ONLY validate the per-technique mappings listed (e.g., "T1059 ← mitigated by: M1026, M1042")
      - DO NOT assume all mitigations apply to all techniques
      - DO NOT flag M1016 for T1059 if T1059's mapping doesn't list M1016
      - Example: If control shows "T1059 ← M1026, M1042" then ONLY check M1026 and M1042 for T1059
      - The "Implements mitigations" list is defense-in-depth, not per-technique
   b) If control shows "Claims ALL mitigations apply to ALL techniques":
      - This is old format - check if ALL mitigations are valid for ALL techniques
      - Flag over-claiming (mitigation doesn't apply to that technique per MITRE)
   c) Calculate actual coverage: valid_mappings / total_claimed_mappings

   CRITICAL: Read the per-technique mappings line by line. Do not infer mappings from the full mitigation list.
   CRITICAL: The arrow "←" means "is mitigated by". Only validate what's after the arrow.

2. CHECK INTERNAL CONSISTENCY:
   - Do rationales match control inventory?
   - Are priorities aligned to RAPIDS risk scores?
   - Does after.mmd have all {len(controls)} controls visualized?
   - Does risk reduction make sense given valid mitigations?

3. VERIFY COVERAGE:
   - Are all 6 RAPIDS categories addressed?
   - Do high-risk categories (≥70) have multiple controls?
   - Are critical paths covered by 3+ controls?
   - Are techniques with minimal valid mitigations flagged?

4. VALIDATE ARCHITECT ROADMAP (if provided):
   - Do roadmap items address real gaps?
   - Are verification methods realistic?
   - Do point estimates make sense?

{'='*70}
VALIDATION METHODOLOGY (CHAIN-OF-THOUGHT)
{'='*70}

For each control, follow this exact process:

STEP 1: Read the control format
  Example:
  ```
  Control: LEAST PRIVILEGE
    Implements mitigations (defense-in-depth): M1016, M1018, M1026, M1042
    Per-technique mappings (validate these against MITRE):
      • T1059 ← mitigated by: M1026, M1042
      • T1190 ← mitigated by: M1016, M1026
  ```

STEP 2: For each technique in "Per-technique mappings", extract ONLY what's after the arrow
  T1059: [M1026, M1042]
  T1190: [M1016, M1026]

STEP 3: Check each extracted mitigation against MITRE reference
  T1059 vs M1026: Is M1026 in T1059's MITRE list? (YES → ✅)
  T1059 vs M1042: Is M1042 in T1059's MITRE list? (YES → ✅)
  T1190 vs M1016: Is M1016 in T1190's MITRE list? (YES → ✅)
  T1190 vs M1026: Is M1026 in T1190's MITRE list? (YES → ✅)

STEP 4: Record results
  ✅ All 4 mappings are valid
  ❌ No invalid mappings found

STEP 5: DO NOT check mitigations that aren't listed after the arrow
  ❌ WRONG: "Is M1016 valid for T1059?" (M1016 NOT claimed for T1059)
  ❌ WRONG: "Is M1018 valid for T1059?" (M1018 NOT claimed for T1059)

{'='*70}
FEW-SHOT EXAMPLES
{'='*70}

EXAMPLE 1: Valid Mapping ✅
```
Control: RATE LIMITING
  Implements mitigations: M1033, M1035, M1037
  Per-technique mappings:
    • T1059 ← mitigated by: M1033
    • T1133 ← mitigated by: M1035
    • T1190 ← mitigated by: M1037, M1035

MITRE Reference:
  T1059: [M1033, M1045, M1042, M1038, ...]  ← M1033 is here ✅
  T1133: [M1021, M1030, M1042, M1035, ...]  ← M1035 is here ✅
  T1190: [M1048, M1037, M1030, M1016, M1026, M1050, M1035, ...]  ← M1037, M1035 both here ✅

VALIDATION:
  T1059 → M1033: ✅ VALID (M1033 in T1059's MITRE list)
  T1133 → M1035: ✅ VALID (M1035 in T1133's MITRE list)
  T1190 → M1037: ✅ VALID (M1037 in T1190's MITRE list)
  T1190 → M1035: ✅ VALID (M1035 in T1190's MITRE list)

RESULT: All mappings valid ✅ No gap to report.
```

EXAMPLE 2: Invalid Mapping (Hypothetical) ❌
```
Control: HYPOTHETICAL CONTROL
  Implements mitigations: M1016, M1026
  Per-technique mappings:
    • T1059 ← mitigated by: M1016
    • T1190 ← mitigated by: M1026

MITRE Reference:
  T1059: [M1033, M1045, M1042, M1038, ...]  ← M1016 NOT here ❌
  T1190: [M1048, M1037, M1030, M1016, M1026, ...]  ← M1026 is here ✅

VALIDATION:
  T1059 → M1016: ❌ INVALID (M1016 NOT in T1059's MITRE list)
  T1190 → M1026: ✅ VALID (M1026 in T1190's MITRE list)

RESULT: 1 invalid mapping found ❌
GAP: "HYPOTHETICAL CONTROL claims M1016 mitigates T1059, but M1016 not in T1059's MITRE mitigation list. Valid T1059 mitigations include: M1033, M1045, M1042, M1038, ..."
```

EXAMPLE 3: Common Mistake to Avoid ❌
```
Control: LEAST PRIVILEGE
  Implements mitigations: M1016, M1018, M1026, M1042
  Per-technique mappings:
    • T1059 ← mitigated by: M1026, M1042

WRONG VALIDATION ❌:
  "Control implements M1016, so I should check if M1016 is valid for T1059"
  → NO! M1016 is NOT claimed for T1059 (only M1026, M1042 are)

CORRECT VALIDATION ✅:
  T1059 → M1026: Check MITRE (YES → ✅)
  T1059 → M1042: Check MITRE (YES → ✅)
  Don't check M1016 or M1018 for T1059 (not claimed)

RESULT: All mappings valid ✅ No gap to report.
```

{'='*70}
OUTPUT REQUIREMENTS
{'='*70}

Return JSON with:
- score (0-100, be critical but fair - hybrid approach deserves credit for defense-in-depth)
- breakdown (4 categories, with reasoning)
- gaps (specific issues with severity, affected components, cite specific technique-mitigation pairs)
  - ONLY report gaps for mappings that are actually claimed (after the arrow ←)
  - DO NOT report gaps for mitigations that aren't claimed for that technique
- strengths (what works well, acknowledge valid defense-in-depth strategy)
- improvement_roadmap (how to fix invalid mappings while preserving defense-in-depth)

BE SPECIFIC: Cite control names, technique IDs, mitigation IDs, use MITRE data.
BE FAIR: Defense-in-depth is valid; flag only where mitigations claimed for wrong techniques.
BE CONSTRUCTIVE: Provide actionable recommendations that preserve risk-averse approach.
BE ACCURATE: Follow the chain-of-thought methodology above. Show your work if uncertain.

{'='*70}
JSON OUTPUT SCHEMA
{'='*70}

Respond with ONLY valid JSON matching this schema:

{{
  "score": <integer 0-100>,
  "rating": "<EXCELLENT|GOOD|FAIR|POOR>",
  "breakdown": {{
    "validation_checks": {{"score": <int>, "max": 40, "reasoning": "<string>"}},
    "coverage_metrics": {{"score": <int>, "max": 30, "reasoning": "<string>"}},
    "internal_consistency": {{"score": <int>, "max": 20, "reasoning": "<string>"}},
    "roadmap_validation": {{"score": <int>, "max": 10, "reasoning": "<string>"}}
  }},
  "gaps": [
    {{
      "severity": "<CRITICAL|HIGH|MEDIUM|LOW>",
      "category": "<validation|coverage|consistency|roadmap>",
      "description": "<specific issue with control name, technique ID, mitigation ID>",
      "recommendation": "<how to fix>"
    }}
  ],
  "strengths": [
    "<what works well>"
  ],
  "improvement_roadmap": [
    {{
      "priority": <1-10>,
      "action": "<what to do>",
      "category": "<validation|coverage|consistency>",
      "impact": "<expected improvement>",
      "verification_method": "<how to verify fix>"
    }}
  ]
}}

VALIDATION CHECKS: Before reporting a gap in "validation_checks", double-check:
1. Is this mitigation actually claimed for this technique in the per-technique mappings?
2. Did I read what's after the arrow (←) correctly?
3. Am I confusing "Implements mitigations" with "Per-technique mappings"?

If unsure, DO NOT report the gap. It's better to miss a real issue than report a false positive.
"""

    return prompt


# ============================================================================
# TESTER CRITIC
# ============================================================================

def create_tester_agent(model: Optional[str] = None) -> CriticAgent:
    """
    Create Tester critic agent (prompt-based, no tools).

    Args:
        model: Optional model override

    Returns:
        Configured CriticAgent
    """
    agent = CriticAgent(
        role="Security Tester",
        rubric=TESTER_RUBRIC,
        system_prompt=TESTER_SYSTEM_PROMPT,
        tools=[],  # No tools - prompt-based approach
        model=model
    )

    logger.info("Created Tester critic agent (prompt-based, no tools)")
    return agent


class TesterCritic:
    """
    Enhanced Tester Critic with prompt-based validation.

    Uses embedded MITRE data in prompts (no tool calling required).

    Usage:
        tester = TesterCritic()
        score = tester.critique(artifacts, architect_critique)
    """

    def __init__(self, model: Optional[str] = None):
        self.agent = create_tester_agent(model)
        self.model = model

    def critique(
        self,
        artifacts: ArtifactSet,
        architect_critique: Optional['CritiqueScore'] = None
    ) -> 'CritiqueScore':
        """
        Critique threat assessment quality.

        Args:
            artifacts: ArtifactSet from artifact_extractor
            architect_critique: Optional Architect critique to validate

        Returns:
            CritiqueScore with validation results
        """
        from chatbot.modules.agent_framework import CritiqueScore

        logger.info("Tester: Starting validation critique")

        # Build comprehensive prompt with MITRE data
        prompt = create_tester_prompt(artifacts, architect_critique)

        # Format as ground truth for agent compatibility
        # (Agent expects ground_truth dict, we override prompt anyway)
        minimal_gt = {
            "architecture": "tester_validation",
            "expected_attack_paths": artifacts.tier1_critical["artifact_1_attack_paths"]["paths"],
            "control_recommendations": artifacts.tier1_critical["artifact_2_controls"]["controls"]
        }

        # Override agent's prompt formatter
        original_formatter = self.agent._format_prompt
        self.agent._format_prompt = lambda gt: prompt

        try:
            score = self.agent.critique(minimal_gt)

            # Post-process: Validate gaps to catch false positives
            score = self._validate_gaps(score, artifacts)

            return score
        finally:
            # Restore original formatter
            self.agent._format_prompt = original_formatter

    def _validate_gaps(self, score: 'CritiqueScore', artifacts: ArtifactSet) -> 'CritiqueScore':
        """
        Post-process gaps to remove false positives (LLM hallucinations).

        Checks if gap claims invalid mappings that are actually valid.
        """
        from chatbot.modules.mitre import MitreHelper

        controls = artifacts.tier1_critical["artifact_2_controls"]["controls"]
        mitre = MitreHelper(use_local=True)

        validated_gaps = []
        false_positives = []

        for gap in score.gaps:
            # Check if this is a validation gap about MITRE mappings
            desc = gap.get("description", "").lower()

            if "claims" in desc and ("mitigation" in desc or "technique" in desc):
                # Extract control name, technique, mitigation from description
                # e.g., "LEAST PRIVILEGE claims M1016 for T1213"
                is_false_positive = self._check_if_false_positive(gap, controls, mitre)

                if is_false_positive:
                    false_positives.append(gap)
                    logger.warning(f"Tester: Removed false positive gap: {gap['description'][:100]}...")
                else:
                    validated_gaps.append(gap)
            else:
                # Non-validation gap, keep as-is
                validated_gaps.append(gap)

        if false_positives:
            logger.info(f"Tester: Removed {len(false_positives)} false positive gaps")
            logger.info(f"Tester: Validated gaps: {len(validated_gaps)}/{len(score.gaps)}")

            # Update score - add points back for removed false positives
            # Each false positive in validation_checks costs ~2-3 points
            points_recovered = min(len(false_positives) * 2, 12)  # Cap at 12 points
            score.score = min(100, score.score + points_recovered)

            # Update breakdown
            if "validation_checks" in score.breakdown:
                val_check = score.breakdown["validation_checks"]
                val_check["score"] = min(40, val_check["score"] + points_recovered)
                val_check["reasoning"] += f"\n\nNote: {len(false_positives)} false positive(s) removed via post-validation."

            # Update rating
            if score.score >= 85:
                score.rating = "EXCELLENT"
            elif score.score >= 70:
                score.rating = "GOOD"
            elif score.score >= 50:
                score.rating = "FAIR"
            else:
                score.rating = "POOR"

        score.gaps = validated_gaps
        return score

    def _check_if_false_positive(self, gap: Dict, controls: List[Dict], mitre: MitreHelper) -> bool:
        """
        Check if a validation gap is a false positive.

        Returns True if the gap claims invalid mapping but mapping is actually valid.
        """
        desc = gap.get("description", "")

        # Try to extract control name, technique ID, mitigation ID
        # Simple heuristic: look for patterns like "CONTROL claims M#### for T####"
        import re

        # Pattern: "CONTROL_NAME claims M#### for T####"
        pattern = r"([A-Z\s]+)\s+(?:control\s+)?claims?\s+(M\d+).*?(?:for|addresses?)\s+(T\d+)"
        match = re.search(pattern, desc, re.IGNORECASE)

        if not match:
            # Can't parse, assume it's valid
            return False

        control_name = match.group(1).strip().lower()
        mitigation_id = match.group(2).upper()
        technique_id = match.group(3).upper()

        # Find the control in data
        control = None
        for ctrl in controls:
            if ctrl["control"].lower() == control_name:
                control = ctrl
                break

        if not control:
            # Control not found, can't validate
            return False

        # Check if control actually claims this mitigation for this technique
        technique_coverage = control.get("technique_coverage", {})

        if technique_id not in technique_coverage:
            # Technique not covered by control, gap might be valid
            return False

        claimed_mits = technique_coverage[technique_id]

        if mitigation_id not in claimed_mits:
            # Mitigation NOT claimed for this technique → gap is FALSE POSITIVE
            logger.info(f"False positive: {control_name} does NOT claim {mitigation_id} for {technique_id}")
            logger.info(f"  Actual coverage for {technique_id}: {claimed_mits}")
            return True

        # Mitigation IS claimed, check if it's valid
        official_mits = mitre.get_technique_mitigations(technique_id)
        official_ids = [m["mitigation_id"] for m in official_mits]

        if mitigation_id in official_ids:
            # Mapping is valid but gap claims it's invalid → FALSE POSITIVE
            logger.info(f"False positive: {mitigation_id} IS valid for {technique_id} per MITRE")
            return True

        # Mapping is truly invalid, gap is correct
        return False


# ============================================================================
# MAIN (for testing)
# ============================================================================

if __name__ == "__main__":
    import sys
    from pathlib import Path

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python3 -m chatbot.modules.tester_critic <report_dir>")
        print("Example: python3 -m chatbot.modules.tester_critic report_samples/example_architecture")
        sys.exit(1)

    report_dir = sys.argv[1]

    print(f"\n{'='*70}")
    print("TESTER CRITIC TEST")
    print(f"{'='*70}\n")

    # Load artifacts
    from chatbot.modules.artifact_extractor import extract_artifacts

    print(f"Loading artifacts from: {report_dir}")
    artifacts = extract_artifacts(report_dir)

    print(f"  Tier 1: {artifacts.completeness['tier1']['count']}/5 artifacts")
    print(f"  Tier 2: {artifacts.completeness['tier2']['count']}/5 artifacts")

    # Load Architect critique if exists
    architect_critique = None
    architect_path = Path(report_dir) / "04_architect_critique.json"
    if architect_path.exists():
        print(f"\nLoading Architect critique...")
        with open(architect_path) as f:
            architect_data = json.load(f)
            # Convert to CritiqueScore (simplified)
            from chatbot.modules.agent_framework import CritiqueScore
            architect_critique = CritiqueScore(
                role=architect_data.get("role", "Architect"),
                score=architect_data.get("score", 0),
                max_score=architect_data.get("max_score", 100),
                rating=architect_data.get("rating", "UNKNOWN"),
                breakdown=architect_data.get("breakdown", {}),
                gaps=architect_data.get("gaps", []),
                strengths=architect_data.get("strengths", []),
                improvement_roadmap=architect_data.get("improvement_roadmap", [])
            )
        print(f"  Architect score: {architect_critique.score}/100 ({architect_critique.rating})")

    # Run Tester
    print(f"\nRunning Tester critic...\n")
    tester = TesterCritic()
    score = tester.critique(artifacts, architect_critique)

    # Display results
    print(f"\n{'='*70}")
    print("TESTER RESULTS")
    print(f"{'='*70}\n")

    print(f"Score: {score.score}/100 ({score.rating})")

    print(f"\n📊 Breakdown:")
    for category, data in score.breakdown.items():
        cat_score = data.get('score', 0)
        cat_max = data.get('max', 0)
        reasoning = data.get('reasoning', 'N/A')[:100]
        print(f"  {category}: {cat_score}/{cat_max}")
        print(f"    {reasoning}...")

    print(f"\n🔍 Gaps Found: {len(score.gaps)}")
    for i, gap in enumerate(score.gaps[:5], 1):
        severity = gap.get('severity', 'UNKNOWN')
        description = gap.get('description', 'No description')
        print(f"  {i}. [{severity}] {description[:100]}...")

    if len(score.gaps) > 5:
        print(f"  ... +{len(score.gaps) - 5} more gaps")

    print(f"\n✅ Strengths: {len(score.strengths)}")
    for i, strength in enumerate(score.strengths[:3], 1):
        print(f"  {i}. {strength}")

    # Save results
    output_path = Path(report_dir) / "05_tester_critique.json"
    with open(output_path, 'w') as f:
        json.dump(score.to_dict(), f, indent=2)

    print(f"\n📄 Saved to: {output_path}")
    print(f"\n{'='*70}\n")
