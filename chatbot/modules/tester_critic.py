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
    """Format controls for prompt."""
    lines = []

    for idx, control in enumerate(controls[:15], 1):  # Limit to 15 for token economy
        name = control.get("control", "Unknown")
        mits = ", ".join(control.get("mitigations", []))
        techs = ", ".join(control.get("techniques", []))
        priority = control.get("priority", "unknown")
        score = control.get("score", 0)

        lines.append(f"  {idx}. {name.upper()} [{priority}] (score: {score:.1f})")
        lines.append(f"     Claims mitigations: {mits}")
        lines.append(f"     Claims techniques: {techs}")

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

1. VALIDATE MITRE MAPPINGS:
   For each control, check:
   - Are claimed mitigations valid?
   - Do mitigations actually address claimed techniques? (use MITRE reference above)
   - Calculate actual coverage: techniques_mitigated / total_techniques

2. CHECK INTERNAL CONSISTENCY:
   - Do rationales match control inventory?
   - Are priorities aligned to RAPIDS risk scores?
   - Does after.mmd have all {len(controls)} controls visualized?

3. VERIFY COVERAGE:
   - Are all 6 RAPIDS categories addressed?
   - Do high-risk categories (≥70) have multiple controls?
   - Are critical paths covered by 3+ controls?

4. VALIDATE ARCHITECT ROADMAP (if provided):
   - Do roadmap items address real gaps?
   - Are verification methods realistic?
   - Do point estimates make sense?

{'='*70}
OUTPUT REQUIREMENTS
{'='*70}

Return JSON with:
- score (0-100, be critical)
- breakdown (4 categories, with reasoning)
- gaps (specific issues with severity, affected components)
- strengths (what works well)
- improvement_roadmap (how to fix issues)

BE SPECIFIC: Cite control names, technique IDs, use MITRE data.
BE CRITICAL: Flag issues even if assessment looks "good enough".
BE CONSTRUCTIVE: Provide actionable recommendations.
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
            return score
        finally:
            # Restore original formatter
            self.agent._format_prompt = original_formatter


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
