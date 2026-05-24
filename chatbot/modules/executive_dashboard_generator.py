"""
Executive Dashboard Generator - Phase 3D Week 3

Generates 00_executive_dashboard.md as single source of truth for CISOs.

Purpose:
- Consolidate deterministic analysis + LLM validation into one coherent report
- Provide clear confidence score (89-99.5%) with validation-based adjustments
- Show unified recommendations (no conflicting scores)
- Give clear, actionable next steps

Fixes Phase 2 Issue #1: Report coherence (CISO confusion from multiple scoring systems)

Input:
- 07_moe_orchestrator.json (MoE pipeline results)
- ground_truth.json (deterministic analysis)
- 04_architect_critique.json (design validation)
- 05_tester_critique.json (MITRE validation)
- 06_red_team_critique.json (exploit difficulty)

Output:
- 00_executive_dashboard.md (unified CISO report)

Version: 1.0 (Phase 3D Week 3)
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


def generate_executive_dashboard(report_dir: str) -> Path:
    """
    Generate unified executive dashboard for CISOs.

    Args:
        report_dir: Path to report directory (e.g., "report/architecture_name")

    Returns:
        Path to generated 00_executive_dashboard.md

    Raises:
        FileNotFoundError: If required input files missing
    """
    report_path = Path(report_dir)
    logger.info(f"Generating executive dashboard for {report_path.name}")

    # Load required data
    moe_result = _load_moe_result(report_path)
    ground_truth = _load_ground_truth(report_path)

    # Optional: Load individual critiques for details
    architect_critique = _load_json_safe(report_path / "04_architect_critique.json")
    tester_critique = _load_json_safe(report_path / "05_tester_critique.json")
    red_team_critique = _load_json_safe(report_path / "06_red_team_critique.json")

    # Generate dashboard content
    dashboard_content = _format_dashboard(
        moe_result=moe_result,
        ground_truth=ground_truth,
        architect_critique=architect_critique,
        tester_critique=tester_critique,
        red_team_critique=red_team_critique,
        architecture_name=report_path.name
    )

    # Write dashboard
    output_path = report_path / "00_executive_dashboard.md"
    with open(output_path, 'w') as f:
        f.write(dashboard_content)

    logger.info(f"Executive dashboard generated: {output_path}")
    return output_path


def _load_moe_result(report_path: Path) -> Dict:
    """Load MoE orchestrator result (required)."""
    moe_path = report_path / "07_moe_orchestrator.json"
    if not moe_path.exists():
        raise FileNotFoundError(
            f"MoE orchestrator result not found: {moe_path}\n"
            f"Run: python3 -m chatbot.modules.agents.orchestrators.moe_orchestrator {report_path}"
        )

    with open(moe_path) as f:
        return json.load(f)


def _load_ground_truth(report_path: Path) -> Dict:
    """Load ground truth (required)."""
    gt_path = report_path / "ground_truth.json"
    if not gt_path.exists():
        raise FileNotFoundError(
            f"Ground truth not found: {gt_path}\n"
            f"Run: python3 -m chatbot.main --gen-arch-truth <architecture.mmd>"
        )

    with open(gt_path) as f:
        return json.load(f)


def _load_json_safe(file_path: Path) -> Optional[Dict]:
    """Load JSON file if exists, return None otherwise."""
    if not file_path.exists():
        logger.warning(f"Optional file not found: {file_path}")
        return None

    with open(file_path) as f:
        return json.load(f)


def _format_dashboard(
    moe_result: Dict,
    ground_truth: Dict,
    architect_critique: Optional[Dict],
    tester_critique: Optional[Dict],
    red_team_critique: Optional[Dict],
    architecture_name: str
) -> str:
    """Format executive dashboard content."""

    # Extract key data
    confidence = moe_result.get("confidence", {})
    risk_transform = moe_result.get("risk_transformation", {})
    consensus = moe_result.get("consensus_recommendations", {})
    improvement_options = moe_result.get("improvement_options", {})
    expert_validations = moe_result.get("expert_validations", {})

    # Format timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Build dashboard
    dashboard = f"""# Executive Security Dashboard

**Architecture:** {architecture_name}
**Analysis Date:** {timestamp}
**Confidence:** {confidence.get('final', 0):.1f}% — {confidence.get('interpretation', 'Unknown')}

> 📋 **This is your primary security report.** All other files (`01_executive_summary.md`, `02_technical_report.md`, etc.) provide supporting details. Start here.

---

## 🎯 Executive Summary

Your architecture has been analyzed using **ThreatAssessor v1.3**, combining deterministic threat modeling with AI-validated assessments.

### How This Analysis Was Performed

**Our 3-Layer Validation Process:**

```
Layer 1: Deterministic Analysis (99.5% confidence)
         └─> Identified threats, attack paths, and recommended controls
         └─> Output: ground_truth.json (source of truth)
              ↓
Layer 2: AI Validation (3 independent experts)
         ├─> Architect: Validated design quality ({confidence.get('adjustments', {}).get('architect', 0)*100:+.1f}% adjustment)
         ├─> Tester: Validated MITRE mappings ({confidence.get('adjustments', {}).get('tester', 0)*100:+.1f}% adjustment)
         └─> Red Team: Assessed exploit difficulty ({confidence.get('adjustments', {}).get('red_team', 0)*100:+.1f}% adjustment)
              ↓
Layer 3: This Dashboard (Final: {confidence.get('final', 0):.1f}% confidence)
         └─> Consensus recommendations based on expert agreement
```

**Result:** Your analysis is **{confidence.get('final', 0):.1f}% confident** — {confidence.get('interpretation', 'N/A')}

### Key Findings

**Overall Security Posture:**
- **Current Risk:** {risk_transform.get('current', 0)}/100
- **Target Risk (with controls):** {risk_transform.get('target', 0)}/100
- **Risk Reduction:** {risk_transform.get('reduction_percent', 0)}%

**Analysis Confidence:**
- **Base (Deterministic):** {confidence.get('base', 0):.1f}% — Industry-standard threat modeling
- **Validated (AI):** {confidence.get('final', 0):.1f}% — After design, technical, and offensive security review
- **Interpretation:** {confidence.get('interpretation', 'N/A')}

### Validation Results

Our analysis was validated by three independent AI security experts:

| Expert | Role | Confidence Adjustment | Status |
|--------|------|----------------------|--------|
| **Architect** | Design Quality | {confidence.get('adjustments', {}).get('architect', 0)*100:+.1f}% | {_get_validation_status(expert_validations.get('architect', {}))} |
| **Tester** | MITRE Validation | {confidence.get('adjustments', {}).get('tester', 0)*100:+.1f}% | {_get_validation_status(expert_validations.get('tester', {}))} |
| **Red Team** | Exploit Difficulty | {confidence.get('adjustments', {}).get('red_team', 0)*100:+.1f}% | {_get_validation_status(expert_validations.get('red_team', {}))} |

{_format_validation_summary(expert_validations)}

---

## 📊 Consensus Recommendations

Our experts agree on the following priority actions:

### 🔴 Critical — **KNOWN (≥2 experts independently agree)**

{_format_consensus_items(consensus.get('critical', []), 'critical')}

### 🟡 High Priority — **KNOWN or UNSURE (see per-item label)**

{_format_consensus_items(consensus.get('high', []), 'high')}

### 🔵 For Review — **UNSURE (single expert, needs human verification)**

{_format_consensus_items(consensus.get('review', []), 'review')}

{_format_blindspots(consensus.get('blindspots', []))}
{_format_contradictions(consensus.get('contradictions', []))}

---

## 💼 Business Decision: Implementation Options

Choose your security investment level based on risk tolerance and budget:

### Option 1: Quick Wins (Recommended for Immediate Risk Reduction)
{_format_improvement_option(improvement_options.get('quick_wins', {}))}

### Option 2: Recommended Target ⭐ (Best ROI)
{_format_improvement_option(improvement_options.get('recommended', {}))}

### Option 3: Maximum Security (Comprehensive)
{_format_improvement_option(improvement_options.get('maximum', {}))}

---

## 🎬 Next Steps: How to Use This Analysis

**For CISOs (Executive Decision):**

1. **✅ Start Here** — You're reading the right file (`00_executive_dashboard.md`)
   - Review consensus recommendations below (🔴 Critical items need immediate action)
   - Choose implementation option (Quick Wins, Recommended ⭐, or Maximum)
   - Check confidence score: {confidence.get('final', 0):.1f}% — {confidence.get('interpretation', 'N/A')}

2. **Optional Deep Dive** — If you want more context:
   - `01_executive_summary.md` — Alternate business summary (legacy format)
   - `02_technical_report.md` — Detailed MITRE threat analysis
   - `08_improvement_summary.md` — Technical implementation guide

**For Engineering Teams (Implementation):**

1. **Start with Action Plan** — `03_action_plan.md`
   - Phased implementation roadmap
   - Timeline and cost estimates

2. **Visual Roadmaps** — See improvement diagrams:
   - `08b_recommended_target.mmd` ⭐ — Critical + High priority controls (recommended)
   - `08a_quick_wins.mmd` — Critical only (1-2 weeks)
   - `08c_maximum_security.mmd` — All controls (6+ months)

3. **Technical Details** — `02_technical_report.md`
   - MITRE ATT&CK techniques
   - Attack path analysis
   - Control specifications

**Validation Trail (For Audit/Compliance):**

This dashboard consolidates findings from:
- **Layer 1:** `ground_truth.json` — Deterministic analysis ({confidence.get('base', 0):.1f}% confidence)
- **Layer 2A:** `04_architect_critique.json` — Design quality validation
- **Layer 2B:** `05_tester_critique.json` — MITRE mapping validation
- **Layer 2C:** `06_red_team_critique.json` — Exploit difficulty assessment
- **Layer 3:** `07_moe_orchestrator.json` — Consensus synthesis (technical data)

**Result:** All validation data combined into this executive dashboard ({confidence.get('final', 0):.1f}% final confidence)
- Consensus synthesis (`07_moe_orchestrator.json`)

---

## 📈 Confidence Breakdown

**How we calculate confidence:**

```
Base Confidence: {confidence.get('base', 0):.1f}% (Deterministic Analysis)
  × Architect: {1 + confidence.get('adjustments', {}).get('architect', 0):.3f} ({confidence.get('adjustments', {}).get('architect', 0)*100:+.1f}%)
  × Tester:    {1 + confidence.get('adjustments', {}).get('tester', 0):.3f} ({confidence.get('adjustments', {}).get('tester', 0)*100:+.1f}%)
  × Red Team:  {1 + confidence.get('adjustments', {}).get('red_team', 0):.3f} ({confidence.get('adjustments', {}).get('red_team', 0)*100:+.1f}%)
= Final: {confidence.get('final', 0):.1f}%
```

**Interpretation:**
- **95-100%:** Exceptional confidence — Analysis validated, minimal gaps
- **90-95%:** Excellent confidence — Minor validation gaps, recommendations solid
- **85-90%:** Good confidence — Some gaps, recommendations valid
- **80-85%:** Acceptable confidence — Several gaps, review recommended
- **<80%:** Needs review — Significant gaps found

Your analysis: **{confidence.get('final', 0):.1f}%** — {confidence.get('interpretation', 'N/A')}

---

## 🔗 Report Navigation

**Start here (you are here):**
- `00_executive_dashboard.md` — This document (CISO summary)

**Detailed reports:**
- `01_executive_summary.md` — Business-friendly overview
- `02_technical_report.md` — Technical threat analysis
- `03_action_plan.md` — Implementation roadmap

**Validation reports:**
- `04_architect_critique.json` — Design quality assessment
- `05_tester_critique.json` — MITRE validation
- `06_red_team_critique.json` — Exploit difficulty
- `07_moe_orchestrator.json` — Consensus synthesis (technical)

**Implementation guides:**
- `08_improvement_summary.md` — Human-readable implementation guide
- `08a_quick_wins.mmd` — Critical controls only (visual)
- `08b_recommended_target.mmd` — Critical + High priority (visual) ⭐
- `08c_maximum_security.mmd` — All controls (visual)

**Diagrams:**
- `before.mmd` — Current architecture (no controls)
- `after.mmd` — Improved architecture (all recommended controls)

**Raw data:**
- `ground_truth.json` — Deterministic analysis (source of truth)

---

**Generated:** {timestamp}
**Tool:** ThreatAssessor v1.3 (Phase 3D)
**Confidence:** {confidence.get('final', 0):.1f}%
**Status:** Production Ready
"""

    return dashboard


def _get_validation_status(validation: Dict) -> str:
    """Get validation status emoji + text."""
    status = validation.get('validation_status', 'UNKNOWN')

    if status == "PASS":
        return "✅ PASS"
    elif status == "MINOR_GAPS":
        return "⚠️ Minor Gaps"
    elif status == "MAJOR_GAPS":
        return "🔴 Major Gaps"
    else:
        return "❓ Unknown"


def _format_validation_summary(expert_validations: Dict) -> str:
    """Format validation summary section."""
    lines = []

    for expert_name, validation in expert_validations.items():
        gaps_count = len(validation.get('gaps', []))
        strengths_count = len(validation.get('strengths', []))

        lines.append(f"**{expert_name.title()}:** {strengths_count} strengths, {gaps_count} gaps")

    return "\n".join(lines)


def _format_consensus_items(items: list, priority: str) -> str:
    """Format consensus recommendation items."""
    if not items:
        return f"*No {priority} priority items identified.*\n"

    lines = []
    for idx, item in enumerate(items, 1):
        desc = item.get('description', 'No description')
        source = item.get('source', '')
        label = item.get('confidence_label', 'UNSURE')
        evidence = item.get('evidence', '')

        lines.append(f"{idx}. **{desc}**")
        if source:
            lines.append(f"   - *Source:* {source}")
        lines.append(f"   - *Confidence:* {label}")
        if evidence:
            lines.append(f"   - *Evidence:* {evidence}")
        lines.append("")

    return "\n".join(lines)


def _format_improvement_option(option: Dict) -> str:
    """Format improvement option details."""
    if not option:
        return "*Option not available.*\n"

    items = option.get('items', [])
    item_list = '\n'.join(f"  - {i}" for i in items) if items else "  *No items listed.*"
    residual = option.get('residual', '')
    practical = option.get('practical_verdict', '')

    return f"""
- **Effort:** {option.get('effort', 'Not estimated')}
- **Estimated Cost:** {option.get('cost', 'cost not estimated')}
- **Risk Reduction:** {option.get('risk_reduction', 'Not estimated')}
{f'- **Practical:** {practical}' if practical else ''}
- **Items:**
{item_list}
{f'- **Residual risk:** {residual}' if residual else ''}
"""


def _format_blindspots(blindspots: list) -> str:
    """Format blindspots section — gaps all three critics structurally missed."""
    if not blindspots:
        return ""

    lines = ["### 🔍 Blindspots — Gaps All Experts Missed\n"]
    lines.append("*These are areas no critic could see due to rubric scope — highest priority for human review.*\n")
    for idx, b in enumerate(blindspots, 1):
        lines.append(f"{idx}. **{b.get('description', '')}**")
        if b.get('why_missed'):
            lines.append(f"   - *Why missed:* {b['why_missed']}")
        if b.get('recommendation'):
            lines.append(f"   - *Action:* {b['recommendation']}")
        lines.append("")
    return "\n".join(lines)


def _format_contradictions(contradictions: list) -> str:
    """Format contradictions section — where experts disagree."""
    if not contradictions:
        return ""

    lines = ["### ⚠️ Expert Disagreements — Human Judgment Required\n"]
    for idx, c in enumerate(contradictions, 1):
        lines.append(f"{idx}. **{c.get('topic', '')}**")
        lines.append(f"   - 🏛️ Architect/Tester: {c.get('architect_view', '')}")
        lines.append(f"   - 🎯 Red Team: {c.get('tester_or_redteam_view', '')}")
        if c.get('root_cause_explanation'):
            lines.append(f"   - *Root cause:* {c['root_cause_explanation']}")
        if c.get('human_action'):
            lines.append(f"   - *Human action:* {c['human_action']}")
        lines.append(f"   - *Resolution:* {c.get('resolution', 'UNSURE — human review needed')}")
        lines.append("")
    return "\n".join(lines)


# ============================================================================
# CLI INTERFACE
# ============================================================================

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s"
    )

    if len(sys.argv) < 2:
        print("Usage: python3 -m chatbot.modules.executive_dashboard_generator <report_dir>")
        print("Example: python3 -m chatbot.modules.executive_dashboard_generator report/10_complex_enterprise")
        sys.exit(1)

    report_dir = sys.argv[1]

    try:
        output_path = generate_executive_dashboard(report_dir)
        print(f"\n✅ Executive dashboard generated: {output_path}\n")
    except Exception as e:
        print(f"\n❌ ERROR: {e}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
