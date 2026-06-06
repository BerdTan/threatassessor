"""
Improvement Summary Generator - Phase 3D Week 3

Generates human-readable improvement summaries from MoE orchestrator consensus.

Updates (Week 3):
- Remove cryptic dict strings (fixes Phase 2 Issue #3)
- Cross-reference 00_executive_dashboard.md (single source of truth)
- Integrate confidence scores from dashboard
- Professional business-friendly output

Outputs: 08_improvement_summary.md

Version: 2.0 (Phase 3D Week 3 - Enhanced for dashboard integration)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_summary(report_dir: str, orchestrator_result: Optional[Dict] = None) -> str:
    """
    Generate human-readable improvement summary from orchestrator consensus.

    Args:
        report_dir: Path to report directory
        orchestrator_result: Optional orchestrator result dict (will read from file if not provided)

    Returns:
        Path to generated summary file
    """
    report_path = Path(report_dir)

    # Load orchestrator report if not provided
    if orchestrator_result is None:
        orch_file = report_path / "07_orchestrator_report.json"
        if not orch_file.exists():
            logger.warning(f"Orchestrator report not found: {orch_file}")
            return None

        with open(orch_file, 'r') as f:
            orchestrator_result = json.load(f)

    # Load ground truth for additional context
    gt_file = report_path / "ground_truth.json"
    ground_truth = {}
    if gt_file.exists():
        with open(gt_file, 'r') as f:
            ground_truth = json.load(f)

    # Extract key metrics (supports both MoE and legacy formats)
    arch_name = orchestrator_result.get("architecture", "Unknown")

    # Check if MoE format (Phase 3D)
    if "expert_validations" in orchestrator_result:
        # MoE format: Use confidence and extract scores from expert_validations
        confidence_data = orchestrator_result.get("confidence", {})
        confidence = confidence_data.get("final", 0)

        expert_validations = orchestrator_result.get("expert_validations", {})
        arch_score = expert_validations.get("architect", {}).get("original_score", 0)
        test_score = expert_validations.get("tester", {}).get("original_score", 0)
        red_exploit = expert_validations.get("red_team", {}).get("original_score", 0)
        red_defense = 100 - red_exploit

        # Use confidence as composite equivalent
        composite_score = int(confidence)
        composite_rating = confidence_data.get("interpretation", "GOOD").split(" - ")[0]
    else:
        # Legacy format (Phase 3C): Use composite scores
        composite = orchestrator_result.get("composite", {})
        composite_score = composite.get("score", 0)
        composite_rating = composite.get("rating", "UNKNOWN")

        individual_scores = orchestrator_result.get("individual_scores", {})
        arch_score = individual_scores.get("architect", {}).get("score", 0)
        test_score = individual_scores.get("tester", {}).get("score", 0)
        red_team = individual_scores.get("red_team", {})
        red_exploit = red_team.get("exploit_score", 0)
        red_defense = red_team.get("defense_score", 0)

        confidence = orchestrator_result.get("confidence", {}).get("final", 0)

    # Get roadmap items
    unified_roadmap = orchestrator_result.get("unified_roadmap", [])
    recommended_target = orchestrator_result.get("recommended_target", {})

    # Count controls from ground truth
    controls_present = ground_truth.get("controls_present", [])
    control_recommendations = ground_truth.get("control_recommendations", [])

    # Get improvement options
    improvement_options = orchestrator_result.get("improvement_options", {})
    consensus_recs = orchestrator_result.get("consensus_recommendations", {})

    # Read MoE orchestrator file for blackhat adjustment (prefer moe over legacy)
    moe_orch = {}
    for fname in ("07_moe_orchestrator.json", "07_orchestrator_report.json"):
        p = report_path / fname
        if p.exists():
            try:
                with open(p) as f:
                    moe_orch = json.load(f)
                break
            except Exception:
                pass
    bh_adjustment = moe_orch.get("adjustments", {}).get("blackhat", None)

    # Build summary content (Week 3 enhanced format)
    content = f"""# Technical Implementation Guide

**Architecture:** {arch_name}
**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}
**Analysis Confidence:** {confidence:.1f}%

> This report summarises what the MoE expert panel validated and which improvements to prioritise.
> For the underlying threat analysis, see [`09_threat_model.md`](09_threat_model.md) (RAPIDS scores,
> threat actors, trust boundaries) and [`10_adr_report.md`](10_adr_report.md) (per-path control decisions).
> For the phased implementation schedule, see [`03_action_plan.md`](03_action_plan.md).

---

## Quick Reference

**Overall Assessment:**
- **Final Confidence:** {confidence:.1f}% — {composite_rating}
- **Design Quality (Architect):** {arch_score}/100
- **MITRE Validation (Tester):** {test_score}/100
- **Defense Strength (Red Team):** {red_defense}/100 (exploit difficulty: {red_exploit}/100)

**Key Insight:** {_generate_key_finding(composite_score, arch_score, test_score, red_defense)}

**Recommended Next Step:** Review [{len(consensus_recs.get('critical', []))} critical items](00_executive_dashboard.md#-critical-all-3-experts-agree--high-confidence) in executive dashboard

---

## Current State Assessment

### Strengths

{_generate_strengths(orchestrator_result, controls_present)}

### Critical Gaps

{_generate_gaps(orchestrator_result, unified_roadmap)}

---

## Improvement Paths

{_generate_improvement_paths(orchestrator_result, unified_roadmap, composite_score)}

---

## Consensus Recommendations

Items all 3 agents agree on (highest confidence):

{_generate_consensus_table(unified_roadmap)}

---

## Implementation Roadmap

{_generate_roadmap(unified_roadmap, composite_score, recommended_target)}

---

## Visual Comparisons

**Before (Current State):**
- Controls present: {len(controls_present)}
- Composite score: {composite_score}/100
- Exploit difficulty: {red_exploit}/100 ({_interpret_exploit_score(red_exploit)})

**After (Recommended Target):**
- Additional controls: {len(control_recommendations)}
- Target composite: {recommended_target.get('score', 'N/A')}/100
- Target exploit: {recommended_target.get('exploit_score', 'N/A')}/100
- Risk reduction: {_calculate_risk_reduction(composite_score, recommended_target.get('score', composite_score))}%

---

## Next Steps

1. Review improvement options with stakeholders
2. Select target (Quick Wins / Recommended / Maximum Security)
3. Review corresponding diagram files:
   - `08a_quick_wins.mmd` - Critical items only (1-2 weeks)
   - `08b_recommended_target.mmd` - Critical + High (1-3 months) ⭐ **RECOMMENDED**
   - `08c_maximum_security.mmd` - All improvements (6+ months)
4. Prioritize controls based on budget and timeline
5. Begin implementation

---

Generated by: ThreatAssessor v1.3
**Orchestrator Report:** 07_orchestrator_report.json
**Architecture:** {arch_name}
**Confidence:** {confidence}%
"""

    # --- Layer 2D: Blackhat section (appended when 06b_blackhat_critique.json exists) ---
    bh_path = report_path / "06b_blackhat_critique.json"
    if bh_path.exists():
        try:
            with open(bh_path) as f:
                bh = json.load(f)
            bh_score = bh.get("score", 0)
            bh_rating = bh.get("rating", "UNKNOWN")
            breakdown = bh.get("breakdown", {})
            chains = breakdown.get("chained_exploit_findings", [])
            stealth = breakdown.get("stealth_score", 0)
            stealthy_techs = breakdown.get("stealthy_techniques", [])
            gaps = breakdown.get("mitigation_gaps_for_chains", [])
            unique = breakdown.get("uniqueness_vs_critics", {})
            new_findings = unique.get("new_findings_not_in_redteam", [])
            shared_nodes = breakdown.get("shared_nodes", {})

            # Confidence impact sentence
            if bh_adjustment is not None and bh_adjustment != 0.0:
                adj_pct = abs(bh_adjustment * 100)
                conf_impact = (
                    f"This finding reduced final confidence by **{adj_pct:.0f}%** "
                    f"(from the base Layer 2A–2C result)."
                )
            elif bh_adjustment == 0.0:
                conf_impact = "Cross-chain risk is within acceptable bounds — no confidence adjustment applied."
            else:
                conf_impact = ""

            # Chain difficulty framing
            if bh_score <= 30:
                chain_framing = "low — cross-path chaining is difficult with current controls"
            elif bh_score <= 60:
                chain_framing = "moderate — some paths share nodes an attacker could pivot through"
            else:
                chain_framing = "high — attacker can chain paths with minimal additional effort"

            bh_section = f"""
---

## Layer 2D: Blackhat Cross-Path Analysis

> The Blackhat critic analyses all attack paths together, looking for chain-exploitation risk
> that single-path critics (Architect, Tester, Red Team) cannot see. It is the only agent
> that reasons about an attacker pivoting from one path to another via shared nodes.

**Cross-chain score:** {bh_score}/100 ({bh_rating}) — chain risk is {chain_framing}.
{conf_impact}

"""
            if shared_nodes:
                pivot_list = ", ".join(
                    f"`{node}` (on {len(paths)} path(s))"
                    for node, paths in list(shared_nodes.items())[:4]
                )
                bh_section += f"**Pivot nodes (shared across paths):** {pivot_list}\n\n"

            if chains:
                bh_section += f"**Chained exploit paths identified ({len(chains)}):**\n"
                for c in chains[:5]:
                    bh_section += f"- {c}\n"
                bh_section += "\n"

            if stealth > 0:
                tech_str = f" ({', '.join(stealthy_techs)})" if stealthy_techs else ""
                bh_section += (
                    f"**Stealth score:** {stealth} Defense Evasion technique(s) in chains{tech_str}. "
                    f"{'An attacker using these techniques would evade detection controls on individual paths.' if stealth >= 2 else ''}\n\n"
                )

            if gaps:
                bh_section += "**Cross-path gaps not addressed by single-path controls:**\n"
                for g in gaps[:5]:
                    bh_section += f"- {g}\n"
                bh_section += "\n"

            if new_findings:
                bh_section += "**Findings unique to Blackhat (not raised by Red Team):**\n"
                for nf in new_findings[:3]:
                    bh_section += f"- {nf}\n"
                bh_section += "\n"

            bh_section += (
                "_These findings are reflected in [`09_threat_model.md`](09_threat_model.md) "
                "and [`11_final.mmd`](11_final.mmd)._\n"
            )

            content += bh_section
        except Exception as exc:
            logger.warning(f"Blackhat section skipped in 08: {exc}")

    # Write summary file
    output_file = report_path / "08_improvement_summary.md"
    with open(output_file, 'w') as f:
        f.write(content)

    logger.info(f"Generated improvement summary: {output_file}")
    return str(output_file)


def _generate_key_finding(composite: int, arch: int, test: int, defense: int) -> str:
    """Generate 1-2 sentence key finding."""
    if composite < 50:
        return f"Architecture has significant security gaps. Design quality ({arch}/100) and validation ({test}/100) are acceptable, but defense strength ({defense}/100) needs immediate improvement."
    elif composite < 70:
        return f"Architecture is moderately secure with {composite}/100 composite score. Primary focus should be on enhancing defense mechanisms (currently {defense}/100 strength)."
    else:
        return f"Architecture is well-defended with {composite}/100 composite score. Focus on incremental improvements to reach excellence (90+)."


def _generate_strengths(orch: Dict, controls_present: List[str]) -> str:
    """Extract strengths from all agents."""
    strengths = []

    # From architect
    arch_roadmap = orch.get("individual_scores", {}).get("architect", {}).get("roadmap", [])
    if arch_roadmap:
        strengths.append(f"- **Design:** {arch_roadmap[0].get('strength', 'Well-structured architecture') if arch_roadmap else 'N/A'}")

    # From controls present
    if len(controls_present) > 5:
        strengths.append(f"- **Existing Controls:** {len(controls_present)} security controls already implemented")

    # From red team
    red_team = orch.get("individual_scores", {}).get("red_team", {})
    if red_team.get("defense_score", 0) > 40:
        strengths.append("- **Defense Depth:** Multiple layers of defense make exploitation difficult")

    return "\n".join(strengths) if strengths else "- Basic security posture established"


def _generate_gaps(orch: Dict, roadmap: List[Dict]) -> str:
    """Extract critical gaps from all agents."""
    gaps = []

    # Critical items from roadmap
    critical_items = [item for item in roadmap if item.get("priority") == "CRITICAL"]

    for item in critical_items[:5]:  # Top 5
        source = item.get("source", "Unknown")
        action = item.get("action", "N/A")

        # Truncate long actions
        if len(action) > 100:
            action = action[:97] + "..."

        gaps.append(f"- **{source}:** {action}")

    return "\n".join(gaps) if gaps else "- No critical gaps identified"


def _generate_improvement_paths(orch: Dict, roadmap: List[Dict], current_score: int) -> str:
    """Generate 3 improvement path options."""

    # Quick wins (CRITICAL only)
    critical_items = [item for item in roadmap if item.get("priority") == "CRITICAL" and item.get("quick_win")]
    quick_target = min(current_score + 10, 100)
    quick_effort = "1-2 weeks"
    quick_cost = "$10K-$50K"

    # Recommended (CRITICAL + some HIGH)
    rec_target = orch.get("recommended_target", {}).get("score", current_score + 20)
    rec_effort = "1-3 months"
    rec_cost = "$75K-$200K"

    # Maximum (all items)
    max_target = min(current_score + 30, 95)
    max_effort = "6+ months"
    max_cost = "$300K-$600K"

    return f"""### Option 1: Quick Wins ({quick_effort}, {quick_cost})

**Target:** {current_score} → {quick_target} composite (+{quick_target - current_score} points)

**Changes:**
- Fix {len(critical_items)} critical validation gaps
- Address high-priority security holes
- Low-hanging fruit with immediate impact

**Diagram:** See `08a_quick_wins.mmd`

**ROI:** **High** - Low cost, immediate security improvement

---

### Option 2: Recommended Target ({rec_effort}, {rec_cost}) ⭐ **RECOMMENDED**

**Target:** {current_score} → {rec_target} composite (+{rec_target - current_score} points)

**Changes:**
- All critical items from Option 1
- High-priority controls validated by all 3 agents
- Key design improvements

**Diagram:** See `08b_recommended_target.mmd`

**ROI:** **Excellent** - Balanced cost/benefit, realistic timeline

---

### Option 3: Maximum Security ({max_effort}, {max_cost})

**Target:** {current_score} → {max_target} composite (+{max_target - current_score} points)

**Changes:**
- Everything from Option 2
- Medium-priority enhancements
- Advanced security features

**Diagram:** See `08c_maximum_security.mmd`

**ROI:** **Diminishing returns** - Only for high-security environments"""


def _generate_consensus_table(roadmap: List[Dict]) -> str:
    """Generate table of consensus recommendations."""
    if not roadmap:
        return "No consensus items identified."

    rows = []
    rows.append("| Priority | Recommendation | Source | Effort | Impact |")
    rows.append("|----------|----------------|--------|--------|--------|")

    for item in roadmap[:10]:  # Top 10
        priority = item.get("priority", "N/A")
        action = item.get("action", "N/A")
        source = item.get("source", "N/A")
        effort = item.get("effort", "N/A")
        impact = item.get("impact", "N/A")

        # Truncate long text
        if len(action) > 50:
            action = action[:47] + "..."
        if len(impact) > 30:
            impact = impact[:27] + "..."

        rows.append(f"| {priority} | {action} | {source} | {effort} | {impact} |")

    return "\n".join(rows)


def _generate_roadmap(roadmap: List[Dict], current_score: int, rec_target: Dict) -> str:
    """Generate implementation timeline."""

    # Group by priority
    critical = [item for item in roadmap if item.get("priority") == "CRITICAL"]
    high = [item for item in roadmap if item.get("priority") == "HIGH"]
    medium = [item for item in roadmap if item.get("priority") == "MEDIUM"]

    target1 = min(current_score + 10, 100)
    target2 = rec_target.get("score", current_score + 20)
    target3 = min(current_score + 30, 95)

    sections = []

    if critical:
        sections.append(f"""1. **Week 1-2:** Quick wins (critical gaps)
   - [ ] {len(critical)} critical items
   - Expected: {current_score} → {target1}""")

    if high:
        sections.append(f"""2. **Month 1-3:** Recommended target
   - [ ] All critical items from Week 1-2
   - [ ] {len(high)} high-priority items
   - Expected: {current_score} → {target2}""")

    if medium:
        sections.append(f"""3. **Month 3-6:** Maximum security (optional)
   - [ ] All items from Month 1-3
   - [ ] {len(medium)} medium-priority enhancements
   - Expected: {current_score} → {target3}""")

    return "\n\n".join(sections) if sections else "No specific roadmap items."


def _interpret_exploit_score(exploit: int) -> str:
    """Interpret exploit difficulty score."""
    if exploit < 30:
        return "very difficult"
    elif exploit < 50:
        return "difficult"
    elif exploit < 70:
        return "moderate"
    else:
        return "easy"


def _calculate_risk_reduction(current: int, target: int) -> int:
    """Calculate % risk reduction."""
    if current == 0:
        return 0
    reduction = ((target - current) / (100 - current)) * 100
    return max(0, int(reduction))
