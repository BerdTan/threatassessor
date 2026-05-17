"""
MMD Improvement Generator

Phase 3C+: Generates stepped improvement MMD diagrams from orchestrator consensus.

Outputs:
- 08a_quick_wins.mmd - CRITICAL controls only
- 08b_recommended_target.mmd - CRITICAL + HIGH controls
- 08c_maximum_security.mmd - All controls (CRITICAL + HIGH + MEDIUM)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Set, Tuple

logger = logging.getLogger(__name__)


def generate_improvement_mmds(report_dir: str, orchestrator_result: Dict = None) -> List[str]:
    """
    Generate 3 stepped improvement MMD diagrams.

    Args:
        report_dir: Path to report directory
        orchestrator_result: Optional orchestrator result (not used currently)

    Returns:
        List of paths to generated MMD files
    """
    report_path = Path(report_dir)

    # Load ground truth for control recommendations
    gt_file = report_path / "ground_truth.json"
    if not gt_file.exists():
        logger.error(f"Ground truth not found: {gt_file}")
        return []

    with open(gt_file, 'r') as f:
        ground_truth = json.load(f)

    # Load original MMD (before.mmd)
    before_file = report_path / "before.mmd"
    if not before_file.exists():
        logger.error(f"Before diagram not found: {before_file}")
        return []

    with open(before_file, 'r') as f:
        original_mmd = f.read()

    # Get control recommendations with priorities
    control_recommendations = ground_truth.get("control_recommendations", [])

    # Filter by priority
    critical_controls = [c for c in control_recommendations if c.get("priority") == "critical"]
    high_controls = [c for c in control_recommendations if c.get("priority") == "high"]
    medium_controls = [c for c in control_recommendations if c.get("priority") == "medium"]

    logger.info(f"Control breakdown: {len(critical_controls)} critical, {len(high_controls)} high, {len(medium_controls)} medium")

    generated_files = []

    # Generate 08a: Quick Wins (CRITICAL only)
    quick_file = _generate_stepped_mmd(
        original_mmd,
        critical_controls,
        report_path / "08a_quick_wins.mmd",
        "CRITICAL",
        "Quick Wins (1-2 weeks) - Critical controls only"
    )
    if quick_file:
        generated_files.append(quick_file)

    # Generate 08b: Recommended Target (CRITICAL + HIGH)
    recommended_file = _generate_stepped_mmd(
        original_mmd,
        critical_controls + high_controls,
        report_path / "08b_recommended_target.mmd",
        "CRITICAL + HIGH",
        "Recommended Target (1-3 months) - Critical and High priority controls"
    )
    if recommended_file:
        generated_files.append(recommended_file)

    # Generate 08c: Maximum Security (ALL)
    maximum_file = _generate_stepped_mmd(
        original_mmd,
        critical_controls + high_controls + medium_controls,
        report_path / "08c_maximum_security.mmd",
        "ALL",
        "Maximum Security (6+ months) - All recommended controls"
    )
    if maximum_file:
        generated_files.append(maximum_file)

    logger.info(f"Generated {len(generated_files)} stepped improvement MMDs")
    return generated_files


def _generate_stepped_mmd(
    original_mmd: str,
    controls: List[Dict],
    output_path: Path,
    priority_level: str,
    description: str
) -> str:
    """
    Generate single stepped MMD diagram with specified controls.

    Args:
        original_mmd: Original architecture MMD content
        controls: List of control recommendation dicts to include
        output_path: Path to output MMD file
        priority_level: Priority level label (CRITICAL, CRITICAL + HIGH, ALL)
        description: Description line for diagram

    Returns:
        Path to generated file
    """
    # Parse original MMD structure
    lines = original_mmd.strip().split('\n')

    # Build improved MMD
    mmd_lines = []
    flowchart_line = None
    structure_lines = []
    edge_declarations = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith('flowchart') or stripped.startswith('graph'):
            flowchart_line = line
        elif '-->' in stripped or '---' in stripped or '<-->' in stripped or '.->' in stripped:
            edge_declarations.append(line)
        elif stripped and not stripped.startswith('%%') and not stripped.startswith('style'):
            structure_lines.append(line)

    # Start building improved diagram
    if flowchart_line:
        mmd_lines.append(flowchart_line)
        mmd_lines.append("")

    # Add header comment
    mmd_lines.append(f"    %% {description}")
    mmd_lines.append(f"    %% Priority Level: {priority_level}")
    mmd_lines.append(f"    %% Controls: {len(controls)}")
    mmd_lines.append("")
    mmd_lines.append("    %% ORIGINAL ARCHITECTURE")

    # Add original structure
    for line in structure_lines:
        mmd_lines.append(line)

    # Add recommended controls section
    mmd_lines.append("")
    mmd_lines.append("    %% RECOMMENDED SECURITY CONTROLS")
    mmd_lines.append("    %% Color-coded by priority:")
    mmd_lines.append("    %% 🔴 CRITICAL (Red) | 🟡 HIGH (Yellow) | 🔵 MEDIUM (Blue)")

    control_nodes = {}
    styling_lines = []

    # Priority color mapping (consistent with Phase 3B++)
    PRIORITY_COLORS = {
        "critical": ("fill:#ff6b6b,stroke:#c92a2a", "🔴"),
        "high": ("fill:#ffd43b,stroke:#fab005", "🟡"),
        "medium": ("fill:#74c0fc,stroke:#339af0", "🔵"),
        "low": ("fill:#90EE90,stroke:#006400", "🟢")
    }

    for rec in controls:
        control = rec.get("control", "").lower()
        control_id = f"NEW_{control.replace(' ', '').replace('/', '').replace('-', '').upper()}"

        # Build control label (simplified from threat_report.py logic)
        control_label = control.title().replace('_', ' ')

        # Add MITRE or RAPIDS info if available
        mitigations = rec.get("mitigations", [])[:2]
        techniques = rec.get("techniques", [])[:2]
        rapids_threats = rec.get("rapids_threats", [])[:2]
        dir_category = rec.get("dir_category", "prevention")
        priority = rec.get("priority", "medium")

        if mitigations:
            control_label += f"<br/>MITRE: {', '.join(mitigations)}"
        if techniques:
            action_verb = {
                "prevention": "Prevents",
                "detect": "Detects",
                "isolate": "Contains",
                "respond": "Recovers"
            }.get(dir_category, "Addresses")
            control_label += f"<br/>{action_verb}: {', '.join(techniques)}"
        elif rapids_threats and not mitigations:
            rapids_categories = [t.replace('_', ' ').title() for t in rapids_threats]
            control_label += f"<br/>RAPIDS: {', '.join(rapids_categories)}"
            control_label += f"<br/>{dir_category.title()}"

        # Choose shape based on control type
        if control in ['waf', 'firewall', 'ids/ips', 'ddos protection']:
            mmd_lines.append(f"    {control_id}[\"{control_label}\"]")
        elif control in ['backup', 'database replication']:
            mmd_lines.append(f"    {control_id}[(\"{control_label}\")]")
        elif control in ['logging', 'siem', 'audit log', 'monitoring']:
            mmd_lines.append(f"    {control_id}[/\"{control_label}\"/]")
        else:
            mmd_lines.append(f"    {control_id}[\"{control_label}\"]")

        # Store styling
        color, emoji = PRIORITY_COLORS.get(priority, PRIORITY_COLORS["medium"])
        styling_lines.append(f"    style {control_id} {color},stroke-width:3px,color:#000000")
        control_nodes[control] = control_id

    # Add connections section
    mmd_lines.append("")
    mmd_lines.append("    %% CONNECTIONS (with integrated controls)")
    mmd_lines.append("    %% Note: Simplified placement - full path-based placement in after.mmd")

    # Add simplified control connections
    # Just show that controls are protecting the architecture
    if control_nodes:
        mmd_lines.append("")
        mmd_lines.append("    %% Controls protect architecture components")
        # We'll just add a comment - actual connections would require full path analysis
        mmd_lines.append("    %% (See after.mmd for detailed control placement)")

    # Add original edges
    mmd_lines.append("")
    mmd_lines.append("    %% ORIGINAL ARCHITECTURE EDGES")
    for edge in edge_declarations:
        mmd_lines.append(edge)

    # Add styling
    mmd_lines.append("")
    for style_line in styling_lines:
        mmd_lines.append(style_line)

    # Write to file
    content = '\n'.join(mmd_lines)
    with open(output_path, 'w') as f:
        f.write(content)

    logger.info(f"Generated {output_path.name} with {len(controls)} controls")
    return str(output_path)
