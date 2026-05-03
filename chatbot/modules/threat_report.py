"""
Threat Assessment Report Generator

Generates comprehensive, user-facing reports for architecture security assessment.
Helps stakeholders make risk-informed decisions about design improvements and mitigations.

Report Formats:
- Executive: High-level summary for decision-makers
- Technical: Detailed analysis for security engineers
- Action Plan: Prioritized recommendations with timeline
"""

import json
from typing import Dict, List
from datetime import datetime
from pathlib import Path

from chatbot.modules.mitre import MitreHelper


def generate_executive_summary(ground_truth: Dict) -> str:
    """
    Generate executive summary for leadership/stakeholders.

    Focus: Business impact, risk level, investment priority
    """
    arch_name = ground_truth["architecture"]
    risk = ground_truth["expected_risk_score"]
    defensibility = ground_truth["expected_defensibility"]
    controls_present = len(ground_truth["controls_present"])
    controls_missing = len(ground_truth["controls_missing"])
    attack_paths = len(ground_truth["expected_attack_paths"])

    # Risk level classification
    if risk >= 80:
        risk_level = "🔴 CRITICAL"
        urgency = "IMMEDIATE ACTION REQUIRED"
        timeline = "24-48 hours"
    elif risk >= 60:
        risk_level = "🟠 HIGH"
        urgency = "Action required within 1 week"
        timeline = "1-2 weeks"
    elif risk >= 40:
        risk_level = "🟡 MEDIUM"
        urgency = "Address in current sprint"
        timeline = "2-4 weeks"
    else:
        risk_level = "🟢 LOW"
        urgency = "Monitor and improve incrementally"
        timeline = "Next quarter"

    # Business impact
    if risk >= 70:
        impact = "Potential data breach, regulatory fines ($1M+), reputational damage"
    elif risk >= 50:
        impact = "Service disruption, data exposure ($100K-$1M), compliance issues"
    else:
        impact = "Limited exposure, manageable risk"

    report = f"""
{'='*80}
EXECUTIVE THREAT ASSESSMENT SUMMARY
{'='*80}

Architecture: {arch_name}
Assessment Date: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}

═══════════════════════════════════════════════════════════════════════════════
RISK OVERVIEW
═══════════════════════════════════════════════════════════════════════════════

Overall Risk Level:      {risk_level} ({risk}/100)
Defensibility Score:     {defensibility}/100
Priority:                {urgency}
Recommended Timeline:    {timeline}

═══════════════════════════════════════════════════════════════════════════════
BUSINESS IMPACT
═══════════════════════════════════════════════════════════════════════════════

Potential Impact:  {impact}
Attack Paths:      {attack_paths} identified paths to critical assets
Security Controls: {controls_present} implemented, {controls_missing} critical gaps

═══════════════════════════════════════════════════════════════════════════════
KEY FINDINGS
═══════════════════════════════════════════════════════════════════════════════

"""

    # RAPIDS assessment summary
    rapids = ground_truth["rapids_assessment"]
    critical_threats = []
    for category, scores in rapids.items():
        if scores["risk"] >= 70:
            critical_threats.append({
                "category": category.replace("_", " ").title(),
                "risk": scores["risk"],
                "defensibility": scores["defensibility"]
            })

    if critical_threats:
        report += "🚨 CRITICAL THREAT CATEGORIES:\n\n"
        for i, threat in enumerate(sorted(critical_threats, key=lambda x: x["risk"], reverse=True)[:3], 1):
            report += f"{i}. {threat['category']:25s} Risk: {threat['risk']:3d}/100  Def: {threat['defensibility']:3d}/100\n"
    else:
        report += "✓ No critical threat categories identified (risk < 70)\n"

    report += "\n"

    # Top attack paths
    if attack_paths > 0:
        report += "🎯 TOP ATTACK PATHS:\n\n"
        for i, ap in enumerate(ground_truth["expected_attack_paths"][:3], 1):
            path_str = " → ".join([n.split()[0] for n in ap["path"][:4]])  # Shorten names
            if len(ap["path"]) > 4:
                path_str += " → ..."
            tier = ap.get("criticality_tier", "UNKNOWN")
            report += f"{i}. [{tier}] {path_str}\n"
            report += f"   Entry: {ap['entry']:20s} Target: {ap['target']}\n"
    else:
        report += "✓ No direct attack paths identified\n"

    report += f"""
═══════════════════════════════════════════════════════════════════════════════
TOP 3 IMMEDIATE ACTIONS
═══════════════════════════════════════════════════════════════════════════════

"""

    # Priority recommendations
    missing_controls = ground_truth.get("controls_missing", [])[:3]
    for i, control in enumerate(missing_controls, 1):
        # Estimate implementation effort
        if control in ["mfa", "logging", "rate limiting"]:
            effort = "< 1 day"
            cost = "$2K"
        elif control in ["waf", "firewall", "backup"]:
            effort = "2-3 days"
            cost = "$5K"
        else:
            effort = "1-2 weeks"
            cost = "$10K+"

        report += f"{i}. Implement {control.upper()}\n"
        report += f"   Effort: {effort}  |  Cost: {cost}  |  Risk Reduction: -15 to -25 points\n\n"

    report += f"""
═══════════════════════════════════════════════════════════════════════════════
RECOMMENDATION
═══════════════════════════════════════════════════════════════════════════════

"""

    if risk >= 70:
        report += f"""
{'URGENT' if risk >= 80 else 'HIGH PRIORITY'} - This architecture requires immediate security improvements.

✗ Current state poses significant risk to business operations
✓ Recommended actions can reduce risk by 40-50 points
✓ Estimated implementation: {timeline}, budget: $15-25K
✓ Expected ROI: 150x (prevented breach cost vs implementation cost)

DECISION: APPROVE IMMEDIATELY
"""
    elif risk >= 40:
        report += f"""
MODERATE PRIORITY - This architecture has security gaps that should be addressed.

✓ Current controls provide baseline protection
✗ {controls_missing} critical gaps remain
✓ Recommended improvements reduce risk to LOW level
✓ Estimated implementation: {timeline}, budget: $10-15K

DECISION: APPROVE FOR CURRENT SPRINT
"""
    else:
        report += f"""
LOW PRIORITY - This architecture has good baseline security.

✓ Strong control coverage ({defensibility}/100 defensibility)
✓ Continue monitoring and incremental improvements
✓ Focus on: {', '.join(missing_controls[:2]) if missing_controls else 'maintaining current posture'}

DECISION: APPROVE FOR NORMAL CYCLE
"""

    report += f"\n{'='*80}\n"

    return report


def generate_technical_report(ground_truth: Dict) -> str:
    """
    Generate technical report for security engineers.

    Focus: Detailed findings, attack path analysis, MITRE techniques, control gaps
    """
    arch_name = ground_truth["architecture"]
    metadata = ground_truth.get("metadata", {})
    arch_type = metadata.get("architecture_type", "unknown")
    node_count = metadata.get("node_count", 0)
    edge_count = metadata.get("edge_count", 0)

    # Initialize MITRE helper for technique lookups
    try:
        mitre = MitreHelper(use_local=True)
    except Exception as e:
        mitre = None  # Graceful fallback if MITRE data unavailable

    report = f"""
{'='*80}
TECHNICAL THREAT ASSESSMENT REPORT
{'='*80}

Architecture: {arch_name}
Type: {arch_type.replace('_', ' ').title()}
Components: {node_count} nodes, {edge_count} connections
Generated: {metadata.get('generated_by', 'parser')}
Assessment Date: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}

═══════════════════════════════════════════════════════════════════════════════
SUMMARY METRICS
═══════════════════════════════════════════════════════════════════════════════

Overall Risk Score:      {ground_truth['expected_risk_score']}/100 (higher = worse)
Defensibility Score:     {ground_truth['expected_defensibility']}/100 (higher = better)
Control Coverage:        {metadata.get('control_coverage', 0):.0%}
Attack Paths Identified: {len(ground_truth['expected_attack_paths'])}

Controls Detected:       {len(ground_truth['controls_present'])}
  {', '.join(ground_truth['controls_present']) if ground_truth['controls_present'] else 'None'}

Critical Gaps:           {len(ground_truth['controls_missing'])}
  {', '.join(ground_truth['controls_missing'][:5])}

═══════════════════════════════════════════════════════════════════════════════
ATTACK PATH ANALYSIS
═══════════════════════════════════════════════════════════════════════════════

"""

    # Detailed attack paths
    for i, ap in enumerate(ground_truth["expected_attack_paths"], 1):
        tier = ap.get("criticality_tier", "UNKNOWN")
        criticality = ap.get("criticality", 0.0)
        path_str = " → ".join(ap["path"])

        report += f"\n[{i}] {tier} PRIORITY (Criticality: {criticality:.2f})\n"
        report += f"{'─'*80}\n"
        report += f"Entry Point:  {ap['entry']}\n"
        report += f"Target:       {ap['target']}\n"
        report += f"Path:         {path_str}\n"
        report += f"Hop Count:    {ap['hop_count']}\n"

        # MITRE techniques with descriptions
        techniques = ap.get("techniques", [])
        if techniques:
            report += f"MITRE ATT&CK:\n"
            for tech_id in techniques:
                # Get technique details from MITRE
                if mitre:
                    tech = mitre.find_technique(tech_id)
                    if tech:
                        tech_name = tech.get('name', 'Unknown')
                        tech_desc = tech.get('description', '')
                        # Truncate description to first sentence for readability
                        if tech_desc:
                            first_sentence = tech_desc.split('.')[0] + '.'
                            if len(first_sentence) > 150:
                                first_sentence = first_sentence[:147] + '...'
                            report += f"  • {tech_id}: {tech_name}\n"
                            report += f"    {first_sentence}\n"
                        else:
                            report += f"  • {tech_id}: {tech_name}\n"
                    else:
                        report += f"  • {tech_id}\n"
                else:
                    report += f"  • {tech_id}\n"

        report += f"Rationale:    {ap.get('rationale', 'N/A')}\n"

    report += f"""

═══════════════════════════════════════════════════════════════════════════════
RAPIDS THREAT ASSESSMENT
═══════════════════════════════════════════════════════════════════════════════

"""

    # RAPIDS categories with details
    rapids = ground_truth["rapids_assessment"]
    for category, scores in sorted(rapids.items(), key=lambda x: x[1]["risk"], reverse=True):
        risk = scores["risk"]
        defensibility = scores["defensibility"]
        rationale = scores["rationale"]

        # Risk level indicator
        if risk >= 70:
            indicator = "🔴 CRITICAL"
        elif risk >= 50:
            indicator = "🟠 HIGH"
        elif risk >= 30:
            indicator = "🟡 MEDIUM"
        else:
            indicator = "🟢 LOW"

        report += f"\n{category.replace('_', ' ').upper()}: {indicator}\n"
        report += f"  Risk:          {risk}/100\n"
        report += f"  Defensibility: {defensibility}/100\n"
        report += f"  Assessment:    {rationale}\n"

    report += f"""

═══════════════════════════════════════════════════════════════════════════════
CONTROL GAP ANALYSIS (RAPIDS-Driven, MITRE-Validated)
═══════════════════════════════════════════════════════════════════════════════

PRIMARY: RAPIDS threat assessment identifies what threats exist
VALIDATION: Attack paths + MITRE techniques confirm exploitability

"""

    # Show detailed control recommendations with confidence and threat context
    control_recs = ground_truth.get("control_recommendations", [])
    if control_recs:
        report += "Recommended Controls (with threat context and confidence):\n\n"
        for i, rec in enumerate(control_recs, 1):
            control = rec["control"]
            priority = rec["priority"]
            confidence = rec.get("confidence", {})
            conf_level = confidence.get("level", "UNKNOWN")
            conf_score = confidence.get("score", 0.0)
            enhanced_rationale = rec.get("enhanced_rationale", rec["rationale"])
            mitigations = rec.get("mitigations", [])
            techniques = rec.get("techniques", [])

            # Confidence indicator
            conf_indicator = "🟢" if conf_level == "HIGH" else "🟡" if conf_level == "MEDIUM" else "🟠"

            report += f"{i}. {control.upper()} ({priority.upper()})\n"
            report += f"   Confidence: {conf_indicator} {conf_level} ({conf_score:.0%})\n"
            report += f"   Addresses: {enhanced_rationale}\n"
            report += f"   MITRE Mitigations: {', '.join(mitigations[:3])}\n"
            report += f"   MITRE Techniques: {', '.join(techniques[:3])}\n"
            report += "\n"
    else:
        # Fallback to simple list if detailed recommendations not available
        missing = ground_truth.get("controls_missing", [])
        if missing:
            report += "Missing Critical Controls:\n"
            for i, control in enumerate(missing, 1):
                report += f"  {i}. {control.upper()}\n"
        else:
            report += "  None - all recommended controls implemented\n"

    report += f"""
Recommended Implementation Order:
  1. Perimeter defenses (WAF, Firewall, DDoS protection)
  2. Authentication (MFA, SSO, least privilege)
  3. Detection & Response (EDR, SIEM, logging)
  4. Data protection (Encryption, backup, DLP)

═══════════════════════════════════════════════════════════════════════════════
ARCHITECTURE-SPECIFIC RECOMMENDATIONS
═══════════════════════════════════════════════════════════════════════════════

"""

    # Type-specific guidance
    if arch_type == "ai_system":
        report += """
AI/LLM System Security:
  • Implement prompt injection filtering (CRITICAL)
  • Add output filtering for PII/sensitive data
  • Enforce rate limiting on API endpoints
  • Implement model access controls
  • Add vector database access controls
  • Monitor for model inversion attacks
"""
    elif arch_type == "web_app":
        report += """
Web Application Security:
  • Deploy Web Application Firewall (WAF)
  • Implement input validation/sanitization
  • Add rate limiting to prevent abuse
  • Enable HTTPS/TLS encryption
  • Implement security headers (CSP, HSTS)
  • Add API authentication/authorization
"""
    elif arch_type == "cloud":
        report += """
Cloud Architecture Security:
  • Implement network segmentation (VPCs, subnets)
  • Enable cloud-native firewall (Security Groups)
  • Configure IAM least privilege access
  • Enable encryption at rest and in transit
  • Implement cloud backup/disaster recovery
  • Enable cloud audit logging
"""
    else:
        report += """
General Security Recommendations:
  • Implement defense-in-depth (multiple control layers)
  • Enable comprehensive logging and monitoring
  • Regular security testing and validation
  • Incident response plan and runbooks
"""

    report += f"\n{'='*80}\n"

    return report


def generate_action_plan(ground_truth: Dict) -> str:
    """
    Generate actionable implementation plan with timeline and owners.

    Focus: Step-by-step roadmap, resource allocation, success metrics
    """
    risk = ground_truth["expected_risk_score"]
    missing = ground_truth.get("controls_missing", [])

    report = f"""
{'='*80}
SECURITY ACTION PLAN
{'='*80}

Architecture: {ground_truth["architecture"]}
Current Risk: {risk}/100
Target Risk:  {max(20, risk - 40)}/100 (after implementation)
Timeline:     {"2-4 weeks" if risk >= 60 else "4-8 weeks"}

═══════════════════════════════════════════════════════════════════════════════
PHASE 1: IMMEDIATE (Week 1) - Quick Wins
═══════════════════════════════════════════════════════════════════════════════

"""

    # Quick wins (easy to implement)
    quick_wins = [c for c in missing if c in ["mfa", "logging", "rate limiting", "audit log"]][:3]

    if quick_wins:
        for i, control in enumerate(quick_wins, 1):
            report += f"Task {i}: Implement {control.upper()}\n"
            report += f"  Owner:    Security Operations Team\n"
            report += f"  Effort:   4-8 hours\n"
            report += f"  Cost:     $500-$1K\n"
            report += f"  Impact:   Risk reduction: -10 to -15 points\n"
            report += f"  Validate: Test with security team\n\n"
    else:
        report += "✓ No quick-win controls needed\n\n"

    report += f"""
═══════════════════════════════════════════════════════════════════════════════
PHASE 2: SHORT-TERM (Weeks 2-3) - Critical Controls
═══════════════════════════════════════════════════════════════════════════════

"""

    # Medium-effort controls
    medium_effort = [c for c in missing if c in ["waf", "firewall", "backup", "encryption", "ids/ips"]][:3]

    if medium_effort:
        for i, control in enumerate(medium_effort, 1):
            report += f"Task {i}: Deploy {control.upper()}\n"
            report += f"  Owner:    Infrastructure / Security Architecture\n"
            report += f"  Effort:   2-3 days\n"
            report += f"  Cost:     $3K-$5K\n"
            report += f"  Impact:   Risk reduction: -15 to -20 points\n"
            report += f"  Validate: Penetration testing\n\n"
    else:
        report += "✓ All critical controls implemented\n\n"

    report += f"""
═══════════════════════════════════════════════════════════════════════════════
PHASE 3: LONG-TERM (Weeks 4-8) - Advanced Protection
═══════════════════════════════════════════════════════════════════════════════

"""

    # Complex controls
    complex_controls = [c for c in missing if c in ["network segmentation", "edr", "siem", "iam"]][:3]

    if complex_controls:
        for i, control in enumerate(complex_controls, 1):
            report += f"Task {i}: Implement {control.upper()}\n"
            report += f"  Owner:    Security Architecture (requires approval)\n"
            report += f"  Effort:   1-2 weeks\n"
            report += f"  Cost:     $10K-$20K\n"
            report += f"  Impact:   Risk reduction: -20 to -30 points\n"
            report += f"  Validate: Red team exercise\n\n"
    else:
        report += "✓ Advanced controls in place\n\n"

    report += f"""
═══════════════════════════════════════════════════════════════════════════════
SUCCESS METRICS & VALIDATION
═══════════════════════════════════════════════════════════════════════════════

Target Metrics (Post-Implementation):
  • Risk Score:        < 40/100
  • Defensibility:     > 70/100
  • Control Coverage:  > 80%
  • Attack Paths:      Mitigated with monitoring

Validation Tests:
  1. Automated security scanning (weekly)
  2. Penetration testing (post-Phase 2)
  3. Red team exercise (post-Phase 3)
  4. Compliance audit (quarterly)

Monitoring & Maintenance:
  • Weekly: Review security logs for anomalies
  • Monthly: Control effectiveness review
  • Quarterly: Re-run threat assessment
  • Annually: Architecture security review

═══════════════════════════════════════════════════════════════════════════════
RESOURCE REQUIREMENTS
═══════════════════════════════════════════════════════════════════════════════

Team Allocation:
  • Security Engineer:    100% (Weeks 1-4)
  • Cloud Architect:      50% (Weeks 2-4)
  • DevOps Engineer:      25% (Weeks 1-4)

Budget Estimate:
  • Phase 1 (Quick Wins):        $2K-$3K
  • Phase 2 (Critical Controls): $10K-$15K
  • Phase 3 (Advanced):          $30K-$40K
  • Total:                       $42K-$58K

Expected ROI:
  • Prevented breach cost:  $420K (industry average)
  • Implementation cost:    $50K
  • ROI:                    840% (8.4x return)

═══════════════════════════════════════════════════════════════════════════════
NEXT STEPS
═══════════════════════════════════════════════════════════════════════════════

[ ] Week 1: Executive approval & budget allocation
[ ] Week 1: Begin Phase 1 implementation
[ ] Week 2: Phase 1 validation testing
[ ] Week 2-3: Phase 2 implementation
[ ] Week 4: Phase 2 validation (penetration test)
[ ] Week 4-8: Phase 3 implementation
[ ] Week 8: Final red team validation
[ ] Week 9: Continuous monitoring begins

{'='*80}
"""

    return report


def generate_before_after_diagrams(
    original_mmd_path: str,
    ground_truth: Dict
) -> tuple[str, str]:
    """
    Generate before.mmd (original) and after.mmd (with recommended controls integrated).

    Returns: (before_mmd_content, after_mmd_content)
    """
    # Read original
    with open(original_mmd_path, 'r') as f:
        original_content = f.read()

    # Parse to understand structure
    lines = original_content.strip().split('\n')

    # Get control recommendations with full details (MITRE, techniques, paths)
    control_recommendations = ground_truth.get('control_recommendations', [])[:5]  # Top 5

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Building after.mmd with {len(control_recommendations)} control recommendations")
    if control_recommendations:
        first_rec = control_recommendations[0]
        logger.info(f"First recommendation type: {type(first_rec)}, has mitigations: {'mitigations' in first_rec if isinstance(first_rec, dict) else False}")

    # Fallback to simple list if detailed recommendations not available
    if not control_recommendations:
        missing_controls = ground_truth.get('controls_missing', [])[:5]
        # Convert to simple format
        control_recommendations = [{"control": c} for c in missing_controls]
        logger.info("Falling back to simple controls_missing list")

    if not control_recommendations:
        # No improvements needed, return same content with note
        after_content = original_content + "\n\n    %% ✓ All recommended controls implemented"
        return (original_content, after_content)

    # Build "after" version with strategically placed controls
    after_lines = []
    structure_lines = []  # All non-edge, non-style lines (nodes, subgraphs, etc.)
    edge_declarations = []
    styling_declarations = []
    flowchart_line = None

    # Parse original structure - preserve order for structure elements
    for line in lines:
        stripped = line.strip()

        if stripped.startswith('flowchart') or stripped.startswith('graph'):
            flowchart_line = line
        elif '-->' in stripped or '---' in stripped or '<-->' in stripped or '.->' in stripped:
            edge_declarations.append(line)
        elif stripped.startswith('style '):
            styling_declarations.append(line)
        elif stripped and not stripped.startswith('%%'):
            # Keep all structure: subgraphs, nodes, end keywords, etc.
            structure_lines.append(line)

    # Rebuild with improvements
    if flowchart_line:
        after_lines.append(flowchart_line)
        after_lines.append("")
        after_lines.append("    %% ORIGINAL ARCHITECTURE")

    # Add all original structure (preserves subgraphs and ordering)
    for line in structure_lines:
        after_lines.append(line)

    # Add recommended control nodes WITH MITRE CONTEXT
    after_lines.append("")
    after_lines.append("    %% RECOMMENDED SECURITY CONTROLS (GREEN)")
    after_lines.append("    %% Format: Control Name<br/>MITRE: M####<br/>Addresses: T####")

    control_nodes = {}
    for rec in control_recommendations:
        control = rec.get("control", rec)  # Handle both dict and string
        if isinstance(control, dict):
            control = control.get("control")

        control_id = f"NEW_{control.replace(' ', '').replace('/', '').replace('-', '').upper()}"

        # Build enhanced label with MITRE context
        control_label = control.title().replace('_', ' ')

        # Add MITRE mitigations and techniques if available
        if isinstance(rec, dict):
            mitigations = rec.get("mitigations", [])[:2]  # Top 2 mitigations
            techniques = rec.get("techniques", [])[:2]     # Top 2 techniques
            attack_paths = rec.get("attack_paths", [])[:3] # Top 3 paths

            logger.debug(f"Control {control}: mits={mitigations}, techs={techniques}, paths={attack_paths}")

            if mitigations:
                control_label += f"<br/>MITRE: {', '.join(mitigations)}"
            if techniques:
                control_label += f"<br/>Blocks: {', '.join(techniques)}"
            if attack_paths:
                path_nums = ', '.join([f"#{p+1}" for p in attack_paths])
                control_label += f"<br/>Paths: {path_nums}"

            logger.debug(f"Final label: {control_label}")

        # Choose shape based on control type
        if control in ['waf', 'firewall', 'ids/ips', 'ddos protection']:
            # Shield-like for perimeter defenses
            after_lines.append(f"    {control_id}[\"{control_label}\"]")
        elif control in ['backup', 'database replication']:
            # Cylinder for data-related
            after_lines.append(f"    {control_id}[(\"{control_label}\")]")
        elif control in ['logging', 'siem', 'audit log', 'monitoring']:
            # Parallelogram for monitoring
            after_lines.append(f"    {control_id}[/\"{control_label}\"/]")
        else:
            # Rectangle for general controls
            after_lines.append(f"    {control_id}[\"{control_label}\"]")

        styling_declarations.append(f"    style {control_id} fill:#90EE90,stroke:#006400,stroke-width:3px,color:#000000")
        control_nodes[control] = control_id

    # Add edges with strategic control placement
    after_lines.append("")
    after_lines.append("    %% CONNECTIONS (with integrated controls)")

    # Parse existing edges to understand flow
    edge_dict = {}  # {(source, target): label}
    for edge_line in edge_declarations:
        stripped = edge_line.strip()
        if '-->' in stripped:
            parts = stripped.split('-->')
            if len(parts) == 2:
                source = parts[0].strip().split()[-1]
                target = parts[1].strip().split()[0]
                edge_dict[(source, target)] = edge_line

    # Find key nodes for control placement
    internet_like = []
    db_like = []
    web_like = []
    all_app_nodes = []

    for node_line in structure_lines:
        stripped = node_line.strip()
        if stripped.startswith('subgraph') or stripped == 'end':
            continue  # Skip subgraph keywords

        lower = node_line.lower()

        # Extract node ID from declaration
        node_id = None
        for part in node_line.split():
            if any(c in part for c in ['(', '[', '{']):
                node_id = part.split('(')[0].split('[')[0].split('{')[0]
                break

        if not node_id:
            continue

        # Categorize nodes
        if any(kw in lower for kw in ['internet', 'external', 'public', 'users', 'mobile', 'client']):
            internet_like.append(node_id)
        if any(kw in lower for kw in ['database', 'db', 'storage', 'store', 'data warehouse', 'cache']):
            db_like.append(node_id)
        if any(kw in lower for kw in ['web', 'app', 'server', 'service', 'api', 'gateway']):
            web_like.append(node_id)
            all_app_nodes.append(node_id)
        elif any(kw in lower for kw in ['orchestrat', 'manager', 'controller', 'worker']):
            all_app_nodes.append(node_id)

    # Add strategic control connections
    controls_placed = set()

    # 1. WAF/Firewall/DDoS: Between Internet and first component
    for control in ['waf', 'firewall', 'ddos protection']:
        if control in control_nodes and internet_like:
            control_id = control_nodes[control]
            # Find what Internet-like nodes connect to
            placed_for_control = False
            for src_node in internet_like[:1]:  # Use first internet-like node
                for (src, dst), edge_line in edge_dict.items():
                    if src == src_node:
                        # Insert control in the middle
                        after_lines.append(f"    {src} --> {control_id}")
                        after_lines.append(f"    {control_id} --> {dst}")
                        controls_placed.add(control)
                        placed_for_control = True
                        break
                if placed_for_control:
                    break

    # 2. Backup/Replication: Connected to database
    for control in ['backup', 'database replication', 'encryption at rest']:
        if control in control_nodes and db_like:
            control_id = control_nodes[control]
            # Connect to first database
            after_lines.append(f"    {db_like[0]} -.->|protected by| {control_id}")
            controls_placed.add(control)

    # 3. Logging/SIEM/Monitoring: Connected to multiple components
    for control in ['logging', 'siem', 'audit log', 'monitoring']:
        if control in control_nodes:
            control_id = control_nodes[control]
            # Connect to key components (prefer app layer first, then data layer)
            if all_app_nodes:
                after_lines.append(f"    {all_app_nodes[0]} -.->|logs to| {control_id}")
            if db_like:
                after_lines.append(f"    {db_like[0]} -.->|audits to| {control_id}")
            controls_placed.add(control)
            break  # Only add one monitoring control

    # 4. Rate limiting/Input validation: At application layer
    for control in ['rate limiting', 'input validation', 'api gateway']:
        if control in control_nodes and (web_like or all_app_nodes):
            control_id = control_nodes[control]
            target = web_like[0] if web_like else all_app_nodes[0]
            after_lines.append(f"    {control_id} --> {target}")
            controls_placed.add(control)

    # 5. MFA/SSO: Before application layer
    for control in ['mfa', 'sso', 'iam']:
        if control in control_nodes and (web_like or all_app_nodes):
            control_id = control_nodes[control]
            target = web_like[0] if web_like else all_app_nodes[0]
            # If there's an internet-like source, place between them
            if internet_like:
                after_lines.append(f"    {internet_like[0]} --> {control_id}")
                after_lines.append(f"    {control_id} --> {target}")
            else:
                after_lines.append(f"    {control_id} --> {target}")
            controls_placed.add(control)

    # 6. AI-specific controls: Connected to LLM/AI components
    for control in ['prompt filtering', 'output filtering', 'sandbox']:
        if control in control_nodes:
            control_id = control_nodes[control]
            # Look for AI-related nodes
            ai_nodes = [n for n in all_app_nodes if any(kw in structure_lines[i].lower()
                       for i, line in enumerate(structure_lines)
                       for kw in ['llm', 'agent', 'prompt', 'ai', 'model']
                       if n in line)]
            if ai_nodes:
                after_lines.append(f"    {control_id} --> {ai_nodes[0]}")
            elif all_app_nodes:
                after_lines.append(f"    {control_id} --> {all_app_nodes[0]}")
            controls_placed.add(control)

    # 7. Network segmentation: Shown as protecting perimeter or data layer
    for control in ['network segmentation', 'ids/ips', 'zero trust']:
        if control in control_nodes:
            control_id = control_nodes[control]
            # Connect between layers
            if db_like and all_app_nodes:
                after_lines.append(f"    {control_id} -.->|isolates| {db_like[0]}")
            elif all_app_nodes:
                after_lines.append(f"    {control_id} -.->|protects| {all_app_nodes[0]}")
            controls_placed.add(control)

    # 8. Policy/process controls: Show as protecting entire architecture
    # These are process-level controls that don't fit into data flow
    process_controls = [
        'least privilege', 'patching', 'vulnerability scanning', 'vulnerability management',
        'user training', 'phishing simulation', 'code signing', 'integrity monitoring',
        'threat intelligence', 'auto-update', 'container scanning', 'secrets management'
    ]
    for control in process_controls:
        if control in control_nodes:
            control_id = control_nodes[control]
            # Connect to ALL components as a policy overlay
            # Pick a representative node to show the policy applies
            if all_app_nodes:
                after_lines.append(f"    {control_id} -.->|applies to all| {all_app_nodes[0]}")
            elif db_like:
                after_lines.append(f"    {control_id} -.->|applies to all| {db_like[0]}")
            controls_placed.add(control)

    # 9. Other controls: Add remaining original edges and annotate with unplaced controls
    for edge_line in edge_declarations:
        after_lines.append(edge_line)

    # Add note for unplaced controls
    all_control_names = [rec.get("control") if isinstance(rec, dict) else rec for rec in control_recommendations]
    unplaced = set(all_control_names) - controls_placed
    if unplaced:
        after_lines.append("")
        after_lines.append(f"    %% Additional recommended: {', '.join(unplaced)}")

    # Add styling
    after_lines.append("")
    for style_line in styling_declarations:
        after_lines.append(style_line)

    after_content = '\n'.join(after_lines)
    return (original_content, after_content)


def save_report(report: str, output_path: str, format_type: str = "md"):
    """Save report to file."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, 'w') as f:
        f.write(report)

    return output_path


def generate_report_package(
    original_mmd_path: str,
    ground_truth: Dict,
    output_dir: str = "report"
) -> Dict[str, str]:
    """
    Generate complete report package with organized folder structure.

    Returns dict with paths to all generated files.
    """
    arch_name = Path(original_mmd_path).stem
    report_base = Path(output_dir) / arch_name
    report_base.mkdir(parents=True, exist_ok=True)

    # Generate reports
    exec_report = generate_executive_summary(ground_truth)
    tech_report = generate_technical_report(ground_truth)
    action_report = generate_action_plan(ground_truth)

    # Generate before/after diagrams
    before_mmd, after_mmd = generate_before_after_diagrams(original_mmd_path, ground_truth)

    # Save all files
    paths = {
        "ground_truth": save_report(
            json.dumps(ground_truth, indent=2),
            str(report_base / "ground_truth.json"),
            "json"
        ),
        "executive": save_report(
            exec_report,
            str(report_base / "01_executive_summary.md")
        ),
        "technical": save_report(
            tech_report,
            str(report_base / "02_technical_report.md")
        ),
        "action_plan": save_report(
            action_report,
            str(report_base / "03_action_plan.md")
        ),
        "before_diagram": save_report(
            before_mmd,
            str(report_base / "before.mmd")
        ),
        "after_diagram": save_report(
            after_mmd,
            str(report_base / "after.mmd")
        ),
        "readme": str(report_base / "README.md")
    }

    # Generate README
    readme_content = f"""# Threat Assessment Report: {arch_name}

## Report Structure

```
{arch_name}/
├── README.md                    # This file
├── ground_truth.json           # Raw assessment data
├── 01_executive_summary.md     # For decision-makers
├── 02_technical_report.md      # For security engineers
├── 03_action_plan.md           # For project managers
├── before.mmd                  # Current architecture (Mermaid)
└── after.mmd                   # Recommended improvements (Mermaid)
```

## Quick Start

### View Reports

1. **Executive Summary** - For business stakeholders
   - Risk level: {ground_truth['expected_risk_score']}/100
   - Decision: {'APPROVE IMMEDIATELY' if ground_truth['expected_risk_score'] >= 70 else 'APPROVE FOR SPRINT'}
   - Read: `01_executive_summary.md`

2. **Technical Report** - For security engineers
   - MITRE techniques, attack paths, RAPIDS assessment
   - Read: `02_technical_report.md`

3. **Action Plan** - For implementation teams
   - Phased roadmap, resource allocation, timeline
   - Read: `03_action_plan.md`

### Visualize Architecture

#### Before (Current State)
```bash
# View with Mermaid viewer
cat before.mmd

# Or render at: https://mermaid.live/
```

#### After (With Recommended Controls)
```bash
# View improved architecture
cat after.mmd

# Green hexagons = Recommended new controls
```

## Key Metrics

| Metric | Value |
|--------|-------|
| **Risk Score** | {ground_truth['expected_risk_score']}/100 (higher = worse) |
| **Defensibility** | {ground_truth['expected_defensibility']}/100 (higher = better) |
| **Controls Present** | {len(ground_truth['controls_present'])} |
| **Critical Gaps** | {len(ground_truth['controls_missing'])} |
| **Attack Paths** | {len(ground_truth['expected_attack_paths'])} identified |

## RAPIDS Threat Assessment

"""

    # Add RAPIDS summary
    rapids = ground_truth['rapids_assessment']
    for category, scores in sorted(rapids.items(), key=lambda x: x[1]['risk'], reverse=True):
        risk = scores['risk']
        icon = "🔴" if risk >= 70 else ("🟠" if risk >= 50 else "🟡" if risk >= 30 else "🟢")
        readme_content += f"- {icon} **{category.replace('_', ' ').title()}**: Risk {risk}/100, Def {scores['defensibility']}/100\n"

    readme_content += f"""

## Top 3 Recommendations

"""

    # Add top recommendations
    for i, control in enumerate(ground_truth.get('controls_missing', [])[:3], 1):
        readme_content += f"{i}. Implement **{control.upper()}**\n"

    readme_content += f"""

## Generated

- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M UTC')}
- **Engine**: {ground_truth.get('metadata', {}).get('generated_by', 'parser')}
- **Architecture Type**: {ground_truth.get('metadata', {}).get('architecture_type', 'unknown')}

## Visual Improvements (Before → After)

The `after.mmd` diagram shows **where and how** to integrate recommended controls:

"""

    # Add specific improvements explanation
    controls_present_set = set(ground_truth.get('controls_present', []))
    for control in ground_truth.get('controls_missing', [])[:5]:
        if control in ['waf', 'firewall', 'ddos protection']:
            readme_content += f"- 🟢 **{control.title()}**: Add as perimeter defense (between Internet and application)\n"
        elif control in ['backup', 'database replication']:
            readme_content += f"- 🟢 **{control.title()}**: Connect to database with replication flow\n"
        elif control in ['logging', 'siem', 'audit log', 'monitoring']:
            readme_content += f"- 🟢 **{control.title()}**: Collect logs from web servers and databases\n"
        elif control in ['rate limiting', 'input validation']:
            readme_content += f"- 🟢 **{control.title()}**: Protect application layer before web server\n"
        elif control in ['mfa', 'sso']:
            readme_content += f"- 🟢 **{control.title()}**: Add authentication layer before application access\n"
        elif control in ['edr', 'antivirus']:
            readme_content += f"- 🟢 **{control.title()}**: Deploy on endpoints (web servers, workstations)\n"
        else:
            readme_content += f"- 🟢 **{control.title()}**: Deploy as additional security layer\n"

    readme_content += f"""

**Legend:**
- Solid lines (→): Data/traffic flow
- Dotted lines (-.->): Monitoring/replication
- Green nodes (🟢): Recommended new controls

## Next Steps

1. Review executive summary with leadership
2. Assess technical report with security team
3. Plan implementation using action plan roadmap
4. **Visualize improvements with before/after diagrams** to understand placement
"""

    save_report(readme_content, paths["readme"])

    return paths


if __name__ == "__main__":
    # Test with sample ground truth
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 -m chatbot.modules.threat_report <ground_truth.json>")
        sys.exit(1)

    with open(sys.argv[1]) as f:
        gt = json.load(f)

    print("\n" + "="*80)
    print("GENERATING REPORTS")
    print("="*80 + "\n")

    exec_report = generate_executive_summary(gt)
    tech_report = generate_technical_report(gt)
    action_report = generate_action_plan(gt)

    print("Executive Summary:")
    print(exec_report[:500] + "...\n")

    print("Technical Report:")
    print(tech_report[:500] + "...\n")

    print("Action Plan:")
    print(action_report[:500] + "...\n")
