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
import logging
from typing import Dict, List, Optional
from datetime import datetime
from pathlib import Path

from chatbot.modules.mitre import MitreHelper, get_mitre_helper
from chatbot.modules.report_formatter import (
    format_section_header,
    format_metric_dashboard,
    format_before_after_comparison,
    format_task_card,
    format_callout,
    remove_ascii_separators
)

logger = logging.getLogger(__name__)


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

    # Generate report with modern formatting
    report = f"# 📊 Executive Threat Assessment\n\n"
    report += f"**Architecture:** {arch_name} | **Date:** {datetime.now().strftime('%B %d, %Y')}\n\n"

    # Dashboard reference (Phase 3D)
    report += "> 📊 **Primary Report:** See [`01_executive_summary.md`](01_executive_summary.md) for AI-validated analysis with confidence scoring.\n"
    report += "> This file provides deterministic threat assessment details.\n\n"
    report += "---\n\n"

    # Executive Dashboard
    report += format_section_header("Executive Dashboard", "🎯", 2)

    # Calculate ROI
    breach_cost = 420  # Industry avg in $K
    if risk >= 70:
        impl_cost = 50
    elif risk >= 40:
        impl_cost = 30
    else:
        impl_cost = 15
    roi = breach_cost / impl_cost if impl_cost > 0 else 0

    # Risk reduction calculation (for dashboard)
    residual_before = ground_truth.get("residual_risks_before", {})
    residual_after = ground_truth.get("residual_risks_after", {})
    before_score = residual_before.get("overall_residual", risk)
    after_score = residual_after.get("overall_residual", risk * 0.1)
    risk_reduction_pct = int((before_score - after_score) / before_score * 100) if before_score > 0 else 0

    metrics = {
        "risk": {
            "value": f"{risk}/100",
            "label": "Risk Level",
            "icon": risk_level.split()[0]  # Extract emoji
        },
        "defensibility": {
            "value": f"{defensibility}/100",
            "label": "Defensibility",
            "icon": "❌" if defensibility < 30 else "⚠️" if defensibility < 60 else "✅"
        },
        "timeline": {
            "value": timeline,
            "label": "Timeline",
            "icon": "⏰"
        },
        "investment": {
            "value": f"${impl_cost}K",
            "label": f"Investment ({roi:.1f}x ROI)",
            "icon": "💰"
        }
    }

    report += format_metric_dashboard(metrics)

    if risk >= 70:
        report += format_callout(f"{urgency} - Architecture poses critical risk to operations", "danger")
    elif risk >= 40:
        report += format_callout(f"{urgency}", "warning")

    # Business Impact
    report += format_section_header("Business Impact", "💼", 2)
    report += "| Impact Area | Current State | Risk |\n"
    report += "|-------------|---------------|------|\n"

    if risk >= 70:
        report += f"| **Data Security** | Unprotected critical assets | Data breach: $1M+ in fines |\n"
        report += f"| **Availability** | No DDoS/resilience | Service outage: $100K/hour |\n"
        report += f"| **Compliance** | Missing audit controls | Regulatory penalties |\n\n"
        report += f"**Bottom Line:** Without immediate action, organization is vulnerable to attacks with potential ${breach_cost}K impact.\n\n"
    elif risk >= 40:
        report += f"| **Data Security** | Partial protection | Data exposure: $100K-$1M |\n"
        report += f"| **Compliance** | Gaps in audit trail | Potential compliance issues |\n\n"
        report += f"**Bottom Line:** Architecture has security gaps that increase risk exposure.\n\n"
    else:
        report += f"| **Data Security** | Good baseline protection | Low residual risk |\n"
        report += f"| **Compliance** | Adequate controls | Minor improvements needed |\n\n"
        report += f"**Bottom Line:** Architecture has solid security foundation with room for improvement.\n\n"

    # Key Findings
    report += format_section_header("Key Findings", "🚨", 2)

    # RAPIDS assessment summary (Phase 3B-2: Filter metadata keys)
    rapids = ground_truth["rapids_assessment"]
    critical_threats = []
    for category, scores in rapids.items():
        # Skip metadata keys (start with _)
        if category.startswith("_") or not isinstance(scores, dict) or "risk" not in scores:
            continue

        if scores["risk"] >= 70:
            critical_threats.append({
                "category": category.replace("_", " ").title(),
                "risk": scores["risk"],
                "defensibility": scores["defensibility"]
            })

    if critical_threats:
        report += "### 🔥 Critical Threat Categories\n\n"
        report += "| Rank | Category | Risk | Defensibility |\n"
        report += "|------|----------|------|---------------|\n"
        for i, threat in enumerate(sorted(critical_threats, key=lambda x: x["risk"], reverse=True)[:3], 1):
            risk_icon = "🔴" if threat['risk'] >= 80 else "🟠"
            def_icon = "❌" if threat['defensibility'] < 30 else "⚠️"
            report += f"| {i} | **{threat['category']}** | {risk_icon} {threat['risk']}/100 | {def_icon} {threat['defensibility']}/100 |\n"
        report += "\n"
    else:
        report += "✅ No critical threat categories identified (all risks < 70)\n\n"

    # All attack paths
    all_aps = ground_truth["expected_attack_paths"]
    _exec_journey_by_ap = {
        j.get("attack_path_id"): j
        for j in ground_truth.get("user_stories", {}).get("journeys", [])
        if j.get("attack_path_id")
    }
    _exec_corr_n = sum(1 for j in _exec_journey_by_ap.values() if not j.get("no_user_story"))
    if attack_paths > 0:
        journey_note = ""
        if _exec_journey_by_ap:
            journey_note = (
                f" {_exec_corr_n}/{len(_exec_journey_by_ap)} of these paths are "
                f"corroborated by real user workflows — the attacker exploits the same "
                f"routes your users legitimately take."
            )
        report += f"### 🎯 Attack Paths ({attack_paths} identified)\n\n"
        if journey_note:
            report += f"_{journey_note}_\n\n"
        for i, ap in enumerate(all_aps, 1):
            path_str = " → ".join([n.split()[0] for n in ap["path"][:4]])  # Shorten names
            if len(ap["path"]) > 4:
                path_str += " → ..."
            tier = ap.get("criticality_tier", "UNKNOWN")
            tier_icon = "🔴" if "CRITICAL" in tier else "🟠" if "HIGH" in tier else "🟡"
            n_controls = len([c for c in ground_truth.get("control_recommendations", []) if i - 1 in c.get("attack_paths", [])])
            j = _exec_journey_by_ap.get(ap.get("id", ""))
            if j and not j.get("no_user_story"):
                journey_tag = f" · **{j.get('user_role','user')} workflow** — detection can use behavioural baselines"
            elif j and j.get("no_user_story"):
                journey_tag = " · **Post-compromise pivot** — no user baseline, needs network controls"
            else:
                journey_tag = ""
            report += f"{i}. **{tier_icon} {tier}:** {path_str}{journey_tag}\n"
            report += f"   - Entry: {ap['entry']} | Target: {ap['target']} | Controls: {n_controls}\n\n"
    else:
        report += "✅ No direct attack paths identified\n\n"

    # SSP Compliance Posture (for leadership: which mandatory controls are present/missing)
    control_recs = ground_truth.get("control_recommendations", [])
    ssp_recs = [r for r in control_recs if r.get("ssp_context") and r["ssp_context"].get("primary")]
    if ssp_recs:
        ssp_profile_label = ssp_recs[0]["ssp_context"].get("profile", "")
        profile_display = ssp_profile_label.replace("_", " ").title() if ssp_profile_label else ""
        l0_present = [r for r in ssp_recs if r["ssp_context"]["primary"]["level"] == 0]
        l0_missing_recs = [r for r in control_recs if r.get("control") in ground_truth.get("controls_missing", []) and r.get("ssp_context") and r["ssp_context"].get("primary") and r["ssp_context"]["primary"]["level"] == 0]
        l1_recs = [r for r in ssp_recs if r["ssp_context"]["primary"]["level"] == 1]

        report += format_section_header("Policy Compliance Posture", "📋", 2)
        report += f"\n**SSP Baseline:** Singapore Government ICT&SS — {profile_display}\n\n"
        report += "| Level | Controls Mapped | Governance Implication |\n"
        report += "|-------|----------------|------------------------|\n"
        report += f"| **L0 Cardinal** | {len(l0_present)} control(s) | Deviation requires **HQ approval** |\n"
        report += f"| **L1 Basic Hygiene** | {len(l1_recs)} control(s) | Deviation requires **SC risk acceptance** |\n"

        if l0_present:
            l0_names = ", ".join(r["ssp_context"]["primary"]["id"] + " " + r["control"].upper() for r in l0_present[:4])
            report += f"\n**L0 Cardinal controls identified (mandatory — no deviation without HQ approval):**\n"
            report += f"{l0_names}\n\n"

        if l0_missing_recs:
            report += f"**⚠️ Mandatory L0 gaps — HQ approval required if deferred:**\n"
            for r in l0_missing_recs[:3]:
                ctx = r["ssp_context"]
                report += f"- [{ctx['label']}] {r['control'].upper()} — {ctx['primary']['title']}\n"
            report += "\n"

    # Residual Risk Assessment (BEFORE and AFTER)
    if residual_before and residual_after:
        before_score = residual_before.get("overall_residual", 0)
        before_status = residual_before.get("overall_status", "UNKNOWN")
        after_score = residual_after.get("overall_residual", 0)
        after_status = residual_after.get("overall_status", "UNKNOWN")

        # Calculate risk reduction
        risk_reduction = before_score - after_score
        risk_reduction_pct = (risk_reduction / before_score * 100) if before_score > 0 else 0

        # Before/After comparison using formatter
        before_data = {
            "risk": f"{before_score:.1f}/100",
            "status": before_status,
            "controls": controls_present
        }
        after_data = {
            "risk": f"{after_score:.1f}/100",
            "status": after_status,
            "controls": controls_present + controls_missing
        }

        report += format_before_after_comparison(before_data, after_data, "Risk Transformation")

        # Impact callout
        report += f"> **Impact:** 📉 {risk_reduction_pct:.0f}% risk reduction ({risk_reduction:.1f} points) with ${impl_cost}K investment\n\n"
        report += f"**ROI:** {roi:.1f}x return (prevented breach cost: ${breach_cost}K)\n\n"

        report += "**Why Residual Risk Remains:**\n"
        report += "- Zero-day exploits (no patch available)\n"
        report += "- Advanced Persistent Threats (sophisticated attackers)\n"
        report += "- Insider threats with privileged access\n"
        report += "- Social engineering and human error\n\n"

        report += f"**Recommendation:** {residual_after.get('summary', 'Implement recommended controls and monitor quarterly')}\n\n"

    # Top 3 Immediate Actions
    report += format_section_header("Top 3 Immediate Actions", "⚡", 2)

    # Priority recommendations
    missing_controls = ground_truth.get("controls_missing", [])[:3]
    for i, control in enumerate(missing_controls, 1):
        # Estimate implementation effort
        if control in ["mfa", "logging", "rate limiting"]:
            effort = "< 1 day"
            cost = "$2K"
            impact = "-15 to -25 points"
        elif control in ["waf", "firewall", "backup"]:
            effort = "2-3 days"
            cost = "$5K"
            impact = "-15 to -25 points"
        else:
            effort = "1-2 weeks"
            cost = "$10K+"
            impact = "-15 to -25 points"

        task_data = {
            "control": control.title(),
            "owner": "Security Team",
            "effort": effort,
            "cost": cost,
            "impact": impact,
            "validation": "Security team testing"
        }

        report += format_task_card(task_data, "Immediate Actions", i)
        report += "\n"

    # Recommendation
    report += format_section_header("Recommendation", "✅", 2)

    if risk >= 70:
        report += f"### {'🚨 URGENT' if risk >= 80 else '⚠️ HIGH PRIORITY'}\n\n"
        report += "This architecture requires immediate security improvements.\n\n"
        report += "| Assessment | Status |\n"
        report += "|------------|--------|\n"
        report += "| **Current Risk** | ❌ Poses significant risk to business operations |\n"
        report += f"| **Risk Reduction** | ✅ {risk_reduction_pct:.0f}% reduction with recommended controls |\n"
        report += f"| **Timeline** | ⏰ {timeline} |\n"
        report += f"| **Budget** | 💰 ${impl_cost}K (ROI: {roi:.1f}x) |\n"
        report += f"| **Decision** | 🚀 **APPROVE IMMEDIATELY** |\n\n"
    elif risk >= 40:
        report += f"### ⚠️ MODERATE PRIORITY\n\n"
        report += "This architecture has security gaps that should be addressed.\n\n"
        report += "| Assessment | Status |\n"
        report += "|------------|--------|\n"
        report += "| **Current Risk** | ⚠️ Baseline protection with notable gaps |\n"
        report += f"| **Risk Reduction** | ✅ {risk_reduction_pct:.0f}% improvement possible |\n"
        report += f"| **Timeline** | ⏰ {timeline} |\n"
        report += f"| **Budget** | 💰 ${impl_cost}K |\n"
        report += f"| **Decision** | ✅ Approve for next sprint |\n\n"
    else:
        report += f"### ✅ LOW PRIORITY\n\n"
        report += "This architecture has good baseline security.\n\n"
        report += "| Assessment | Status |\n"
        report += "|------------|--------|\n"
        report += f"| **Current Risk** | ✅ Strong control coverage ({defensibility}/100) |\n"
        report += "| **Focus** | Continue monitoring and incremental improvements |\n"
        report += f"| **Priority Controls** | {', '.join(missing_controls[:2]) if missing_controls else 'Maintain current posture'} |\n"
        report += f"| **Decision** | ✅ Approve for normal cycle |\n\n"

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
        mitre = get_mitre_helper()
    except Exception as e:
        mitre = None  # Graceful fallback if MITRE data unavailable

    report = f"# 🔬 Technical Threat Assessment Report\n\n"
    report += f"**Architecture:** {arch_name}  \n"
    report += f"**Type:** {arch_type.replace('_', ' ').title()} | "
    report += f"**Components:** {node_count} nodes, {edge_count} connections  \n"
    report += f"**Generated:** {metadata.get('generated_by', 'parser')} | "
    report += f"**Date:** {datetime.now().strftime('%B %d, %Y')}\n\n"

    # Navigation
    report += "> 📊 **Primary Report:** See [`01_executive_summary.md`](01_executive_summary.md) for validated analysis.\n"
    report += "> **Threat narrative:** [`09_threat_model.md`](09_threat_model.md) — RAPIDS scoring, threat actors, trust boundaries.\n"
    report += "> **Control decisions:** [`10_adr_report.md`](10_adr_report.md) — why each control, at which hop, for which threat.\n\n"
    report += "---\n\n"

    report += format_section_header("Summary Metrics", "📊", 2)
    report += f"**Overall Risk Score:** {ground_truth['expected_risk_score']}/100 (higher = worse)  \n"
    report += f"**Defensibility Score:** {ground_truth['expected_defensibility']}/100 (higher = better)  \n"
    report += f"**Control Coverage:** {metadata.get('control_coverage', 0):.0%}  \n"
    report += f"**Attack Paths Identified:** {len(ground_truth['expected_attack_paths'])}  \n\n"

    report += f"**Controls Detected:** {len(ground_truth['controls_present'])}  \n"
    if ground_truth['controls_present']:
        report += f"  {', '.join(ground_truth['controls_present'])}  \n\n"
    else:
        report += "  None  \n\n"

    report += f"**Critical Gaps:** {len(ground_truth['controls_missing'])}  \n"
    if ground_truth['controls_missing']:
        report += f"  {', '.join(ground_truth['controls_missing'][:5])}  \n\n"

    # Attack Path Analysis
    report += format_section_header("Attack Path Analysis", "🛣️", 2)

    _tech_journey_by_ap = {
        j.get("attack_path_id"): j
        for j in ground_truth.get("user_stories", {}).get("journeys", [])
        if j.get("attack_path_id")
    }

    # Detailed attack paths with improved formatting
    for i, ap in enumerate(ground_truth["expected_attack_paths"], 1):
        tier = ap.get("criticality_tier", "UNKNOWN")
        criticality = ap.get("criticality", 0.0)
        path_str = " → ".join(ap["path"])

        # Path header
        report += f"\n### Path #{i}: {tier} Priority\n\n"

        # Path details table
        report += "| Attribute | Value |\n"
        report += "|-----------|-------|\n"
        report += f"| **Entry Point** | {ap['entry']} |\n"
        report += f"| **Target** | {ap['target']} |\n"
        report += f"| **Attack Path** | {path_str} |\n"
        report += f"| **Hop Count** | {ap['hop_count']} |\n"
        report += f"| **Criticality** | {criticality:.2f} |\n\n"

        # MITRE ATT&CK + ATLAS techniques with descriptions
        techniques = ap.get("techniques", [])
        if techniques:
            mitre_techs = [t for t in techniques if not t.startswith("AML.")]
            atlas_techs = [t for t in techniques if t.startswith("AML.")]

            if mitre_techs:
                report += "**MITRE ATT&CK Techniques:**\n\n"
                for tech_id in mitre_techs:
                    if mitre:
                        tech = mitre.find_technique(tech_id)
                        if tech:
                            tech_name = tech.get('name', 'Unknown')
                            tech_desc = tech.get('description', '')
                            if tech_desc:
                                first_sentence = tech_desc.split('.')[0] + '.'
                                if len(first_sentence) > 120:
                                    first_sentence = first_sentence[:117] + '...'
                                report += f"- **{tech_id}: {tech_name}**  \n"
                                report += f"  {first_sentence}\n\n"
                            else:
                                report += f"- **{tech_id}: {tech_name}**\n\n"
                        else:
                            report += f"- {tech_id}\n\n"
                    else:
                        report += f"- {tech_id}\n\n"

            if atlas_techs:
                report += "**MITRE ATLAS Techniques (AI/ML-specific):**\n\n"
                try:
                    from chatbot.modules.atlas_helper import get_atlas_helper
                    atlas = get_atlas_helper()
                except Exception:
                    atlas = None
                for tech_id in atlas_techs:
                    tech = atlas.get_technique_by_id(tech_id) if atlas else None
                    if tech:
                        tech_name = tech.get('name', tech_id)
                        tech_desc = tech.get('description', '')
                        if tech_desc:
                            first_sentence = tech_desc.split('.')[0] + '.'
                            if len(first_sentence) > 150:
                                first_sentence = first_sentence[:147] + '...'
                            report += f"- **{tech_id}: {tech_name}** *(ATLAS)*  \n"
                            report += f"  {first_sentence}\n\n"
                        else:
                            report += f"- **{tech_id}: {tech_name}** *(ATLAS)*\n\n"
                    else:
                        report += f"- **{tech_id}** *(ATLAS — AI/ML attack technique)*\n\n"

        # Rationale
        rationale = ap.get('rationale', 'N/A')
        report += f"**Analysis:** {rationale}\n"

        # User journey context
        j = _tech_journey_by_ap.get(ap.get("id", ""))
        if j and not j.get("no_user_story"):
            report += f"\n**User journey:** {j.get('story_text', '')}\n"
            chain = j.get("exploitation_chain", "")
            if chain:
                report += f"\n**Exploitation chain:** {chain}\n"
            report += (
                f"\n> **Detection strategy:** Corroborated — a real {j.get('user_role','user')} "
                f"follows this path. Behavioural anomaly detection is viable but must use "
                f"a precise {j.get('user_role','user')} baseline to avoid false positives.\n\n"
            )
        elif j and j.get("no_user_story"):
            report += (
                f"\n> **Detection strategy:** Post-compromise pivot — no normal user follows "
                f"this path. Behavioural baselines cannot help. Use network segmentation, "
                f"east-west traffic inspection, or explicit hop-level alerts.\n\n"
            )

    report += format_section_header("RAPIDS Threat Assessment", "🎯", 2)

    # RAPIDS categories with details (Phase 3B-2: Filter metadata)
    rapids = ground_truth["rapids_assessment"]
    # Filter out metadata keys
    rapids_filtered = {k: v for k, v in rapids.items() if not k.startswith("_") and isinstance(v, dict) and "risk" in v}

    # Create table format for better readability
    report += "\n| Threat Category | Level | Risk Score | Defensibility | Assessment |\n"
    report += "|----------------|-------|------------|---------------|------------|\n"

    for category, scores in sorted(rapids_filtered.items(), key=lambda x: x[1]["risk"], reverse=True):
        risk = scores["risk"]
        defensibility = scores["defensibility"]
        rationale = scores["rationale"]
        category_name = category.replace('_', ' ').title()

        # Handle special case for DoS
        if category.lower() == "dos":
            category_name = "Denial of Service"

        # Risk level indicator
        if risk >= 70:
            indicator = "🔴 CRITICAL"
        elif risk >= 50:
            indicator = "🟠 HIGH"
        elif risk >= 30:
            indicator = "🟡 MEDIUM"
        else:
            indicator = "🟢 LOW"

        # Truncate rationale if too long for table
        rationale_short = rationale if len(rationale) < 60 else rationale[:57] + "..."
        report += f"| {category_name:<14} | {indicator:<13} | {risk}/100 | {defensibility}/100 | {rationale_short} |\n"

    report += "\n"

    report += format_section_header("Control Gap Analysis", "🔍", 2)
    report += "\n**Methodology:** RAPIDS-Driven, MITRE-Validated\n\n"
    report += "- **PRIMARY:** RAPIDS threat assessment identifies what threats exist\n"
    report += "- **VALIDATION:** Attack paths + MITRE techniques confirm exploitability\n\n"

    # Show detailed control recommendations with confidence and threat context
    control_recs = ground_truth.get("control_recommendations", [])
    if control_recs:
        report += "**Recommended Controls:**\n\n"
        report += "| # | Control | Priority | SSP | Confidence | MITRE Mitigations | MITRE Techniques | Threat Context |\n"
        report += "|---|---------|----------|-----|------------|-------------------|------------------|----------------|\n"

        for i, rec in enumerate(control_recs, 1):
            control = rec["control"]
            priority = rec["priority"]
            confidence = rec.get("confidence", {})
            conf_level = confidence.get("level", "UNKNOWN")
            conf_score = confidence.get("score", 0.0)
            enhanced_rationale = rec.get("enhanced_rationale") or rec.get("rationale", "")
            mitigations = rec.get("mitigations", [])
            techniques = rec.get("techniques", [])
            is_gap_control = not rec.get("attack_paths", [])

            # Confidence indicator
            conf_indicator = "🟢" if conf_level == "HIGH" else "🟡" if conf_level == "MEDIUM" else "🟠"

            # Truncate for table readability
            mitigations_str = ", ".join(mitigations[:3])
            if len(mitigations) > 3:
                mitigations_str += f" +{len(mitigations)-3}"

            techniques_str = ", ".join(techniques[:3])
            if len(techniques) > 3:
                techniques_str += f" +{len(techniques)-3}"

            # Gap controls: replace blank/misleading rationale with clear label
            if is_gap_control:
                rationale_short = "Generic hardening — no direct path mapping"
            else:
                rationale_short = enhanced_rationale if len(enhanced_rationale) < 50 else enhanced_rationale[:47] + "..."

            # Inline SSP badge
            ssp_ctx = rec.get("ssp_context")
            if ssp_ctx and ssp_ctx.get("primary"):
                p = ssp_ctx["primary"]
                ssp_cell = f"{ssp_ctx['label']} L{p['level']}"
            else:
                ssp_cell = "—"

            report += f"| {i} | **{control.upper()}** | {priority.upper()} | {ssp_cell} | {conf_indicator} {conf_level} ({conf_score:.0%}) | {mitigations_str} | {techniques_str} | {rationale_short} |\n"

        report += "\n"

        # SSP policy context — detailed block per recommendation
        ssp_blocks = [
            rec for rec in control_recs
            if rec.get("ssp_context") and rec["ssp_context"].get("primary")
        ]
        if ssp_blocks:
            ssp_profile_label = (ssp_blocks[0].get("ssp_context") or {}).get("profile", "")
            profile_display = ssp_profile_label.replace("_", " ").title() if ssp_profile_label else ""
            report += f"**Singapore Government SSP Baseline — {profile_display}**\n\n"
            report += "> L0 = Cardinal (HQ approval required for deviation) | L1 = Basic Hygiene (SC risk acceptance) | L2 = Best Practice (risk-owner acceptance)\n\n"
            for rec in ssp_blocks:
                ctx = rec["ssp_context"]
                primary = ctx["primary"]
                control_label = rec.get("control", rec.get("name", "")).upper()
                report += (
                    f"**{ctx['label']}** `{primary['title']}` — {primary['level_label']}"
                    f" | *Control:* {control_label}\n\n"
                )
                if primary.get("risk_statement"):
                    report += f"  *Why it matters:* {primary['risk_statement']}\n\n"
                if primary.get("recommendation"):
                    report += f"  *How to implement:* {primary['recommendation']}\n\n"
                # List secondary SSP controls
                secondaries = ctx.get("secondaries", [])
                if secondaries:
                    sec_ids = ", ".join(f"{s['id']} ({s['level_label']})" for s in secondaries)
                    report += f"  *Also covered by:* {sec_ids}\n\n"
                report += "---\n\n"

    else:
        # Fallback to simple list if detailed recommendations not available
        missing = ground_truth.get("controls_missing", [])
        if missing:
            report += "Missing Critical Controls:\n"
            for i, control in enumerate(missing, 1):
                report += f"  {i}. {control.upper()}\n"
        else:
            report += "  None - all recommended controls implemented\n"

    report += "\n**Recommended Implementation Order:**\n\n"
    report += "1. Perimeter defenses (WAF, Firewall, DDoS protection)\n"
    report += "2. Authentication (MFA, SSO, least privilege)\n"
    report += "3. Detection & Response (EDR, SIEM, logging)\n"
    report += "4. Data protection (Encryption, backup, DLP)\n\n"

    report += format_section_header("Residual Risk Assessment", "⚖️", 2)
    report += "\n**Key Principle:** Even with ALL recommended controls implemented, residual risk remains.\n"
    report += "No control is 100% effective - this is a realistic assessment for risk acceptance.\n\n"

    # Detailed residual risk per threat
    residual_risks = ground_truth.get("residual_risks", {})
    if residual_risks and "per_threat" in residual_risks:
        report += "| Threat Category      | Initial | Control Effectiveness | Residual | Status   |\n"
        report += "|---------------------|---------|----------------------|----------|----------|\n"

        for threat, data in residual_risks["per_threat"].items():
            # Handle special case for DoS -> Denial of Service
            if threat.lower() == "dos":
                threat_name = "Denial of Service"
            else:
                threat_name = threat.replace("_", " ").title()

            threat_name = threat_name[:20].ljust(20)
            initial = f"{data['initial_risk']}/100"
            effectiveness = f"{data['combined_effectiveness']:.0%}"
            residual = f"{data['residual_risk']}/100"
            status_emoji = {"ACCEPT": "✅", "MONITOR": "⚠️", "MITIGATE": "❌"}.get(data['status'], "❓")
            status = f"{status_emoji} {data['status']}"

            controls_list = [c["name"] for c in data["controls"][:3]]
            if len(data["controls"]) > 3:
                controls_list.append(f"+{len(data['controls'])-3} more")
            controls_str = ", ".join(controls_list)

            report += f"| **{threat_name.strip()}** | {initial:7s} | {effectiveness:20s} | {residual:8s} | {status:8s} |\n"
            report += f"| ↳ *Controls:* {controls_str} | | | | |\n"

        overall_residual = residual_risks.get("overall_residual", 0)
        overall_status = residual_risks.get("overall_status", "UNKNOWN")
        status_emoji = {"ACCEPT": "✅", "MONITOR": "⚠️", "MITIGATE": "❌"}.get(overall_status, "❓")

        report += f"\n**{status_emoji} OVERALL RESIDUAL RISK:** {overall_residual:.1f}/100 ({overall_status})\n\n"

        # Thresholds
        report += "**Risk Acceptance Thresholds:**\n\n"
        report += "- < 10:  ✅ ACCEPT (low risk, quarterly monitoring)\n"
        report += "- 10-20: ⚠️ MONITOR (medium risk, active monitoring required)\n"
        report += "- > 20:  ❌ MITIGATE (high risk, additional controls needed)\n\n"

        # Why residual risk exists
        report += "**Why Residual Risk Exists (No Silver Bullet):**\n\n"
        report += "- Zero-day exploits (no patch available yet)\n"
        report += "- Advanced Persistent Threats (sophisticated techniques)\n"
        report += "- Insider threats with privileged access\n"
        report += "- Social engineering and human error\n"
        report += "- Configuration drift and operational mistakes\n\n"

        # Continuous improvement
        report += "**Continuous Improvement Recommendations:**\n\n"
        report += "- Quarterly threat landscape review\n"
        report += "- Annual penetration testing\n"
        report += "- Bi-annual incident response drills\n"
        report += "- Control effectiveness validation\n"
        report += "- Security awareness training (quarterly)\n\n"

    report += format_section_header("Architecture-Specific Recommendations", "🏗️", 2)

    # ARC Framework Benchmark (if AI system)
    arc_gaps = ground_truth.get("arc_control_gaps")
    if arc_gaps and arch_type == "ai_system":
        report += format_section_header("ARC Framework Control Benchmark", "🤖", 2)
        report += "\n**AI/ML Control Coverage (ARC Framework - 88 Controls):**\n\n"

        overall_cov = arc_gaps.get("overall_coverage", 0)
        deployed = arc_gaps.get("deployed_arc_controls", 0)
        total = arc_gaps.get("total_arc_controls", 0)

        report += f"**Overall Coverage:** {overall_cov:.1f}% ({deployed}/{total} controls deployed)  \n\n"

        # Coverage by category
        report += "| Category | Coverage | Status |\n"
        report += "|----------|----------|--------|\n"

        coverage_by_cat = arc_gaps.get("coverage_by_category", {})
        for cat in ["integrity", "safety", "security", "privacy", "transparency", "accountability", "fairness", "resilience", "societal_impact"]:
            cov = coverage_by_cat.get(cat, 0)
            status = "✅ Good" if cov >= 50 else ("⚠️ Partial" if cov >= 20 else "❌ Critical")
            report += f"| {cat.capitalize():20s} | {cov:5.1f}% | {status} |\n"

        report += "\n"

        # Critical gaps
        critical_gaps = arc_gaps.get("critical_gaps", [])
        if critical_gaps:
            report += "**Critical Gaps (High Risk + Low Coverage):**\n\n"
            for gap in critical_gaps:
                cat = gap["category"]
                risk = gap["risk"]
                cov = gap["coverage"]
                missing = gap["missing_controls"]

                report += f"- **{cat.capitalize()}** (Risk: {risk}/100, Coverage: {cov:.1f}%)\n"
                report += f"  Missing controls: {', '.join(missing[:5])}\n\n"

        report += "\n"

    # Type-specific guidance
    if arch_type == "ai_system":
        report += "**AI/LLM System Security Priorities:**\n\n"
        report += "- Implement prompt injection filtering (CRITICAL)\n"
        report += "- Add output filtering for PII/sensitive data\n"
        report += "- Enforce rate limiting on API endpoints\n"
        report += "- Implement model access controls\n"
        report += "- Add vector database access controls\n"
        report += "- Monitor for model inversion attacks\n\n"
    elif arch_type == "web_app":
        report += "\n**Web Application Security:**\n\n"
        report += "- Deploy Web Application Firewall (WAF)\n"
        report += "- Implement input validation/sanitization\n"
        report += "- Add rate limiting to prevent abuse\n"
        report += "- Enable HTTPS/TLS encryption\n"
        report += "- Implement security headers (CSP, HSTS)\n"
        report += "- Add API authentication/authorization\n\n"
    elif arch_type == "cloud":
        report += "\n**Cloud Architecture Security:**\n\n"
        report += "- Implement network segmentation (VPCs, subnets)\n"
        report += "- Enable cloud-native firewall (Security Groups)\n"
        report += "- Configure IAM least privilege access\n"
        report += "- Enable encryption at rest and in transit\n"
        report += "- Implement cloud backup/disaster recovery\n"
        report += "- Enable cloud audit logging\n\n"
    else:
        report += "\n**General Security Recommendations:**\n\n"
        report += "- Implement defense-in-depth (multiple control layers)\n"
        report += "- Enable comprehensive logging and monitoring\n"
        report += "- Regular security testing and validation\n"
        report += "- Incident response plan and runbooks\n\n"

    # Clean up any remaining ASCII separators
    report = remove_ascii_separators(report, remove_all=True)

    return report


def generate_action_plan(ground_truth: Dict) -> str:
    """
    Generate actionable implementation plan with timeline and owners.

    Focus: Step-by-step roadmap, resource allocation, success metrics
    """
    risk = ground_truth["expected_risk_score"]
    missing = ground_truth.get("controls_missing", [])
    rr_after = ground_truth.get("residual_risks_after", {})
    residual = rr_after.get("overall_residual", None)
    residual_status = rr_after.get("overall_status", "")
    target_str = (
        f"{residual:.1f}/100 ({residual_status})" if residual is not None
        else f"{max(20, risk - 40)}/100 (estimated)"
    )

    report = f"# 📋 Security Action Plan\n\n"
    report += f"**Architecture:** {ground_truth['architecture']}  \n"
    report += f"**Current Risk:** {risk}/100  \n"
    report += f"**Target Risk (post-controls):** {target_str}  \n"
    report += f"**Timeline:** {'2-4 weeks' if risk >= 60 else '4-8 weeks'}\n\n"

    # Navigation
    report += "> 📊 **Primary Report:** See [`01_executive_summary.md`](01_executive_summary.md) for validated recommendations.\n"
    report += "> **Threat analysis:** [`09_threat_model.md`](09_threat_model.md) — what is at risk and why.\n"
    report += "> **Control decisions:** [`10_adr_report.md`](10_adr_report.md) — per-path decision rationale.\n"
    report += "> **MoE validation:** [`08_improvement_summary.md`](08_improvement_summary.md) — expert-validated priority order.\n\n"
    report += "---\n\n"

    # Drive phases from control_recommendations (covers all controls with correct priority)
    control_recs = ground_truth.get("control_recommendations", [])
    # Fall back to controls_missing strings if no recommendations available
    if not control_recs:
        control_recs = [{"control": c, "priority": "high", "attack_paths": []} for c in missing]

    # ADR filter: build the set of controls the ADR mandated at each hop.
    # Recommendations whose control name does not appear in any ADR hop are annotated
    # with adr_gap=True so report tables can flag them — we never drop them, only annotate.
    adrs = ground_truth.get("architecture_decision_records", [])
    if adrs:
        adr_control_names = {
            (ctrl.get("name") or "").lower().strip()
            for adr in adrs
            for hop in (adr.get("hops") or [])
            for ctrl in (hop.get("controls") or [])
            if (ctrl.get("name") or "").strip()
        }
        for rec in control_recs:
            rec_name = (rec.get("control") or "").lower().strip()
            rec["adr_mandated"] = any(
                rec_name in c or c in rec_name
                for c in adr_control_names
            ) if adr_control_names else None

    # Phase buckets: CRITICAL path-mapped → Phase 1, HIGH path-mapped → Phase 2,
    # MEDIUM path-mapped + all gap controls → Phase 3
    phase1 = [r for r in control_recs if r.get("priority", "").lower() == "critical" and r.get("attack_paths")]
    phase2 = [r for r in control_recs if r.get("priority", "").lower() == "high" and r.get("attack_paths")]
    phase3 = [r for r in control_recs if r.get("priority", "").lower() in ("medium", "low") and r.get("attack_paths")]
    gap    = [r for r in control_recs if not r.get("attack_paths")]

    # Deduplicate across phases: a control appearing in a higher-priority phase is
    # removed from all lower phases. Normalise on lower-stripped control name.
    def _dedup_phases(*phases):
        seen: set = set()
        result = []
        for phase in phases:
            unique = []
            for r in phase:
                key = (r.get("control") or "").lower().strip()
                if key not in seen:
                    seen.add(key)
                    unique.append(r)
            result.append(unique)
        return result

    phase1, phase2, phase3, gap = _dedup_phases(phase1, phase2, phase3, gap)

    # Build journey lookup for action plan context
    _ap_journeys = {
        j.get("attack_path_id"): j
        for j in ground_truth.get("user_stories", {}).get("journeys", [])
        if j.get("attack_path_id")
    }
    _all_aps_list = ground_truth.get("control_recommendations", [])  # for index→id mapping
    _ap_id_by_idx = {
        idx: ap.get("id", f"AP-{idx+1}")
        for idx, ap in enumerate(ground_truth.get("expected_attack_paths", []))
    }

    def _journey_cell(ap_indices):
        """Return a short 'Protects' label from journey data for control rows."""
        if not ap_indices or not _ap_journeys:
            return "—"
        roles = []
        has_post = False
        for idx in ap_indices:
            ap_id = _ap_id_by_idx.get(idx)
            if not ap_id:
                continue
            j = _ap_journeys.get(ap_id)
            if j and not j.get("no_user_story"):
                role = j.get("user_role", "user")
                if role not in roles:
                    roles.append(role)
            elif j and j.get("no_user_story"):
                has_post = True
        parts = []
        if roles:
            parts.append(", ".join(roles) + " workflow")
        if has_post:
            parts.append("post-compromise pivot")
        return "; ".join(parts) if parts else "—"

    from chatbot.modules.control_cost_benchmark import lookup as _bench_lookup, _cost_str as _bench_cost_str

    def _control_effort_cost(control_name: str, default_effort: str, default_cost: str):
        result = _bench_lookup(control_name)
        if result:
            effort, low_k, high_k = result
            return (effort, _bench_cost_str(low_k, high_k))
        return (default_effort, default_cost)

    def _phase_table(recs, owner, default_effort, default_cost, impact, validation):
        out = "\n| # | Control | Priority | SSP | Paths Covered | Protects | Owner | Effort | Cost | Impact | Validation |\n"
        out += "|---|---------|----------|-----|---------------|----------|-------|--------|------|--------|------------|\n"
        for i, rec in enumerate(recs, 1):
            ctrl = rec["control"].upper()
            pri  = rec.get("priority", "").upper()
            aps  = rec.get("attack_paths", [])
            paths_str = ", ".join([f"AP#{p+1}" for p in aps]) if aps else "Generic hardening"
            ssp_ctx = rec.get("ssp_context")
            if ssp_ctx and ssp_ctx.get("primary"):
                p = ssp_ctx["primary"]
                level_stars = {"0": "★★★", "1": "★★☆", "2": "★☆☆"}.get(str(p["level"]), "")
                ssp_badge = f"{ssp_ctx['label']} L{p['level']} {level_stars}"
            else:
                ssp_badge = "—"
            protects = _journey_cell(aps)
            adr_flag = "" if rec.get("adr_mandated") is None else (" ✓ADR" if rec.get("adr_mandated") else " ⚠no-ADR")
            effort, cost = _control_effort_cost(rec["control"], default_effort, default_cost)
            out += f"| {i} | **{ctrl}**{adr_flag} | {pri} | {ssp_badge} | {paths_str} | {protects} | {owner} | {effort} | {cost} | {impact} | {validation} |\n"
        return out + "\n"

    report += (
        "> **Effort & cost estimates** are indicative ranges derived from:\n"
        "> - *Config-only controls* — CIS Controls v8 IG1 implementation effort tiers; NIST SP 800-53 Rev 5 (CM/AC families)\n"
        "> - *Tool deployment* — Gartner Market Guide for Security Tools (2024); SANS Security Spending Survey (2024)\n"
        "> - *Process / programme* — NIST SP 800-53 Rev 5 (CA/RA/AT families); CIS Controls v8 IG2 safeguards\n"
        "> - *Architecture changes* — NIST SP 800-207 (Zero Trust Architecture); Gartner Security Architecture Guide (2024)\n"
        "> - *AI / ML controls* — NIST AI RMF 1.0 (Govern/Map/Measure/Manage); OWASP LLM Top 10 (2025)\n"
        ">\n"
        "> Actual figures depend on team size, existing tooling, and environment complexity. Treat as planning inputs, not fixed commitments.\n\n"
    )

    report += format_section_header("Phase 1: Immediate (Week 1) — Critical Path Controls", "⚡", 2)
    if phase1:
        report += _phase_table(phase1, "Security Ops", "4–8 hours", "$500–$1K", "−10 to −15 pts", "Security team test")
    else:
        report += "\n✓ No critical path controls pending\n\n"

    report += format_section_header("Phase 2: Short-Term (Weeks 2–3) — High-Priority Path Controls", "🛡️", 2)
    if phase2:
        report += _phase_table(phase2, "Infra / Sec Arch", "2–3 days", "$3K–$5K", "−10 to −20 pts", "Penetration test")
    else:
        report += "\n✓ All high-priority path controls implemented\n\n"

    report += format_section_header("Phase 3: Medium-Term (Weeks 4–8) — Remaining Path Controls", "🚀", 2)
    if phase3:
        report += _phase_table(phase3, "Sec Arch", "1–2 weeks", "$5K–$15K", "−5 to −15 pts", "Red team exercise")
    else:
        report += "\n✓ All medium-priority path controls implemented\n\n"

    report += format_section_header("Phase 4: Ongoing — Generic Hardening Controls", "🔒", 2)
    report += "\n> These controls address threat scenarios not directly mapped to identified attack paths.\n> They provide defence-in-depth and should be scheduled based on organisational capacity.\n\n"
    if gap:
        report += _phase_table(gap, "Security Ops / Ops", "Varies", "Varies", "Defence-in-depth", "Compliance audit")
    else:
        report += "\n✓ No gap hardening controls pending\n\n"

    report += format_section_header("Success Metrics & Validation", "✅", 2)
    report += "\n**Target Metrics (Post-Implementation):**\n\n"
    report += "  • Risk Score:        < 40/100\n"
    report += "  • Defensibility:     > 70/100\n"
    report += "  • Control Coverage:  > 80%\n"
    report += "  • Attack Paths:      Mitigated with monitoring\n\n"
    report += "**Validation Tests:**\n\n"
    report += "  1. Automated security scanning (weekly)\n"
    report += "  2. Penetration testing (post-Phase 2)\n"
    report += "  3. Red team exercise (post-Phase 3)\n"
    report += "  4. Compliance audit (quarterly)\n\n"
    report += "**Monitoring & Maintenance:**\n"
    report += "  • Weekly: Review security logs for anomalies\n"
    report += "  • Monthly: Control effectiveness review\n"
    report += "  • Quarterly: Residual risk assessment and threat landscape review\n"
    report += "  • Annually: Full architecture security review and penetration testing\n\n"

    report += format_section_header("Residual Risk Monitoring Plan", "📊", 2)

    # Add residual risk monitoring tasks
    residual_risks = ground_truth.get("residual_risks", {})
    if residual_risks and "per_threat" in residual_risks:
        overall_residual = residual_risks.get("overall_residual", 0)
        overall_status = residual_risks.get("overall_status", "UNKNOWN")

        report += f"Post-Implementation Residual Risk: {overall_residual:.1f}/100 ({overall_status})\n\n"

        if overall_status == "ACCEPT":
            report += "\n**Quarterly Monitoring (Low Residual Risk):**\n"
            report += "  • Review control effectiveness quarterly\n"
            report += "  • Monitor for new threats and vulnerabilities\n"
            report += "  • Update controls based on threat landscape\n"
            report += "  • Annual penetration testing to validate controls\n\n"
        elif overall_status == "MONITOR":
            report += "\n**Active Monitoring Required (Medium Residual Risk):**\n"
            report += "  • Monthly security posture reviews\n"
            report += "  • Active threat hunting (weekly)\n"
            report += "  • Incident response drills (quarterly)\n"
            report += "  • Consider additional controls if risk increases\n"
            report += "  • Quarterly penetration testing\n\n"
        else:
            report += "⚠️ CRITICAL: High Residual Risk - Additional Controls Needed\n"
            report += "  • Implement additional controls immediately\n"
            report += "  • Daily security monitoring\n"
            report += "  • Weekly threat intelligence reviews\n"
            report += "  • Monthly red team exercises\n"
            report += "  • Escalate to executive leadership for risk acceptance\n\n"

        # Risk acceptance
        report += "**Risk Acceptance Requirement:**\n\n"
        report += "- [ ] CISO / Security Leadership acknowledges residual risks\n"
        report += "- [ ] Business Owner accepts risks within organizational appetite\n"
        report += "- [ ] Commitment to continuous monitoring and improvement\n\n"
        report += "**Signature:** ________________  **Date:** __________\n\n"
        report += "**Ongoing Activities:**\n\n"
        report += "- Quarterly: Re-run threat assessment\n"
        report += "- Annually: Architecture security review\n\n"

    report += format_section_header("Resource Requirements", "💰", 2)
    report += "\n**Team Allocation:**\n\n"
    report += "- Security Engineer:    100% (Weeks 1-4)\n"
    report += "- Cloud Architect:      50% (Weeks 2-4)\n"
    report += "- DevOps Engineer:      25% (Weeks 1-4)\n\n"
    report += "**Budget Estimate:**\n\n"
    report += "- Phase 1 (Quick Wins):        $2K-$3K\n"
    report += "- Phase 2 (Critical Controls): $10K-$15K\n"
    report += "- Phase 3 (Advanced):          $30K-$40K\n"
    report += "- **Total:**                   **$42K-$58K**\n\n"
    report += "**Expected ROI:**\n\n"
    report += "- Prevented breach cost:  $420K (industry average)\n"
    report += "- Implementation cost:    $50K\n"
    report += "- **ROI:**                **840% (8.4x return)**\n\n"
    # SSP Compliance Checklist (grouped by level)
    ssp_recs_ap = [r for r in control_recs if r.get("ssp_context") and r["ssp_context"].get("primary")]
    if ssp_recs_ap:
        ssp_profile_label_ap = ssp_recs_ap[0]["ssp_context"].get("profile", "")
        profile_display_ap = ssp_profile_label_ap.replace("_", " ").title() if ssp_profile_label_ap else ""
        report += format_section_header("SSP Compliance Checklist", "📜", 2)
        report += f"\n**Policy Baseline:** Singapore Government ICT&SS — {profile_display_ap}\n\n"
        report += "> L0 = Cardinal (deviation → HQ approval) | L1 = Basic Hygiene (deviation → SC risk acceptance) | L2 = Best Practice (deviation → risk-owner acceptance)\n\n"

        for level in [0, 1, 2]:
            level_label = {0: "L0 — Cardinal (Mandatory)", 1: "L1 — Basic Hygiene (Baseline)", 2: "L2 — Best Practice (Conditional)"}[level]
            level_recs = [r for r in ssp_recs_ap if r["ssp_context"]["primary"]["level"] == level]
            if not level_recs:
                continue
            report += f"**{level_label}**\n\n"
            for r in level_recs:
                ctx = r["ssp_context"]
                control_up = r["control"].upper()
                report += f"- [ ] **{ctx['label']}** {control_up} — {ctx['primary']['title']}\n"
            report += "\n"

    report += format_section_header("Next Steps", "📅", 2)
    report += "\n**Implementation Checklist:**\n\n"
    report += "- [ ] Week 1: Executive approval & budget allocation\n"
    report += "- [ ] Week 1: Begin Phase 1 implementation\n"
    report += "- [ ] Week 2: Phase 1 validation testing\n"
    report += "- [ ] Week 2-3: Phase 2 implementation\n"
    report += "- [ ] Week 4: Phase 2 validation (penetration test)\n"
    report += "- [ ] Week 4-8: Phase 3 implementation\n"
    report += "- [ ] Week 8: Final red team validation\n"
    report += "- [ ] Week 9: Continuous monitoring begins\n\n"

    # ── ScrumMaster Action Plan (appended when SM ran) ────────────────────
    sm_plan = ground_truth.get("scrum_master_action_plan", [])
    if sm_plan:
        report += "\n---\n\n"
        report += format_section_header("ScrumMaster Priority Actions", "🧩", 2)
        sm_note = ground_truth.get("scrum_master_synthesis_note", "")
        sm_traj = ground_truth.get("scrum_master_confidence_trajectory", [])
        sm_retriggered = ground_truth.get("scrum_master_critics_retriggered", [])
        sm_redesign = ground_truth.get("scrum_master_redesign_signal", False)

        if sm_note:
            report += f"\n> {sm_note}\n\n"
        if sm_traj and len(sm_traj) > 1:
            traj_str = " → ".join(f"{v:.1f}%" for v in sm_traj)
            report += f"**Confidence trajectory:** {traj_str}\n\n"
        if sm_retriggered:
            report += f"**Critics re-triggered:** {', '.join(sm_retriggered)}\n\n"
        if sm_redesign:
            report += "> ⚠ **Redesign signal:** The ScrumMaster determined that incremental controls alone "
            report += "cannot close the identified gaps. Architectural changes are recommended.\n\n"

        report += "These items represent the ScrumMaster's sharp prioritised list — ranked by risk reduction "
        report += "and implementation effort after cross-critic impediment analysis.\n\n"

        prio_labels = {"critical": "🔴 CRITICAL", "high": "🟠 HIGH", "medium": "🟡 MEDIUM", "low": "⚪ LOW"}
        for i, item in enumerate(sm_plan, 1):
            prio = item.get("priority", "medium").lower()
            label = prio_labels.get(prio, prio.upper())
            report += f"### {i}. {item.get('action', 'Action item')}\n\n"
            report += f"**Priority:** {label}  \n"
            if item.get("rationale"):
                report += f"**Rationale:** {item['rationale']}  \n"
            if item.get("risk_reduction_estimate"):
                report += f"**Risk reduction:** {item['risk_reduction_estimate']}  \n"
            if item.get("effort"):
                report += f"**Estimated effort:** {item['effort']}\n\n"

        sm_bf = ground_truth.get("scrum_master_baseline_feedback")
        if sm_bf:
            report += "#### Engine Improvement Notes\n\n"
            report += "_These notes feed back into future analysis passes — not immediate action items._\n\n"
            for gap in sm_bf.get("ground_truth_gaps", []):
                report += f"- {gap}\n"
            for ctrl in sm_bf.get("weak_controls", [])[:5]:
                report += f"- Weak control (too generic): {ctrl}\n"
            report += "\n"

    # Clean up any remaining ASCII separators
    report = remove_ascii_separators(report, remove_all=True)

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
    # Phase 3B: Visualize ALL recommended controls (no [:5] limit)
    control_recommendations = ground_truth.get('control_recommendations', [])

    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Building after.mmd with {len(control_recommendations)} control recommendations (ALL)")

    # No hard limit - visualize all recommended controls
    # User needs to see complete defense strategy, not truncated view
    # Mermaid can handle 20+ nodes, and users can zoom/scroll if needed
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
    after_lines.append("    %% RECOMMENDED SECURITY CONTROLS (COLOR-CODED BY PRIORITY)")
    after_lines.append("    %% 🔴 CRITICAL = Breaks primary attack paths (implement first)")
    after_lines.append("    %% 🟡 HIGH = Closes validation gaps (implement within 3 months)")
    after_lines.append("    %% 🔵 MEDIUM = Defense-in-depth (implement within 6 months)")
    after_lines.append("    %% 🟢 BASELINE = Security hygiene (ongoing program)")
    after_lines.append("    %% 🟣 HARDENING = Gap-filling controls (baseline security posture)")
    after_lines.append("    %% Format: MITRE controls show M####/T####, RAPIDS controls show threat category")

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
            # Phase 3B: Show ALL information (no truncation) for completeness
            mitigations = rec.get("mitigations", [])[:3]  # Top 3 mitigations (increased from 2)
            techniques = rec.get("techniques", [])[:3]     # Top 3 techniques (increased from 2)
            attack_paths = rec.get("attack_paths", [])     # ALL paths (removed [:3] limit)
            dir_category = rec.get("dir_category", "prevention")  # Get DIR category
            priority = rec.get("priority", "medium")  # Phase 3B++: Get priority for color coding
            rapids_threats = rec.get("rapids_threats", [])  # RAPIDS threat categories

            logger.debug(f"Control {control}: mits={mitigations}, techs={techniques}, paths={len(attack_paths)} paths, dir={dir_category}, priority={priority}, rapids={rapids_threats}")

            # Phase 3B++: Show framework-specific context
            # MITRE controls: Show M####, T####, Paths
            # RAPIDS-only controls: Show RAPIDS category, DIR action
            if mitigations:
                control_label += f"<br/>MITRE: {', '.join(mitigations)}"
            if techniques:
                # Use context-aware verb based on DIR category
                action_verb = {
                    "prevention": "Prevents",    # Stops attack from happening
                    "detect": "Detects",         # Identifies attack in progress
                    "isolate": "Contains",       # Limits damage/spread
                    "respond": "Recovers"        # Restores after breach
                }.get(dir_category, "Addresses")  # Default fallback

                control_label += f"<br/>{action_verb}: {', '.join(techniques)}"
            elif rapids_threats and not mitigations:
                # RAPIDS-only control (no MITRE mapping)
                # Show: RAPIDS category + DIR action for consistency
                rapids_categories = [t.replace('_', ' ').title() for t in rapids_threats[:2]]
                control_label += f"<br/>RAPIDS: {', '.join(rapids_categories)}"

                # Show DIR category as action for consistency with MITRE controls
                dir_action = dir_category.title()  # Prevention, Detect, Isolate, Respond
                control_label += f"<br/>{dir_action}"

            if attack_paths:
                path_nums = ', '.join([f"#{p+1}" for p in attack_paths])
                control_label += f"<br/>Paths: {path_nums}"
            else:
                # Gap-filling control with no specific attack path
                control_label += f"<br/>Hardening"

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

        # Phase 3B++: Priority-based color coding for visual prioritization
        # Color scheme aligned with Phase 3C+ HYBRID_PLAN for consistency
        PRIORITY_COLORS = {
            "critical": "fill:#ff6b6b,stroke:#c92a2a",    # RED - breaks attack paths
            "high": "fill:#ffd43b,stroke:#fab005",         # YELLOW - closes gaps
            "medium": "fill:#74c0fc,stroke:#339af0",       # BLUE - defense-in-depth
            "low": "fill:#90EE90,stroke:#006400",          # GREEN - baseline hygiene
            "hardening": "fill:#dda0dd,stroke:#9370db"     # PURPLE - gap-filling controls
        }

        # Get priority from recommendation (default to medium if not specified)
        control_priority = rec.get("priority", "medium") if isinstance(rec, dict) else "medium"

        # Override priority to "hardening" if this is a gap-filling control (no attack paths)
        is_gap_filling = isinstance(rec, dict) and not rec.get("attack_paths", [])
        if is_gap_filling:
            control_priority = "hardening"

        control_color = PRIORITY_COLORS.get(control_priority, PRIORITY_COLORS["medium"])

        styling_declarations.append(f"    style {control_id} {control_color},stroke-width:3px,color:#000000")
        control_nodes[control] = control_id

    # Add edges with strategic control placement
    after_lines.append("")
    after_lines.append("    %% CONNECTIONS (with integrated controls)")

    # Track control edges vs original edges for color coding
    control_edges = []  # Lines with control connections (will be colored)
    original_edges_start_idx = None  # Where original edges begin

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

    # Phase 3B+: PATH-BASED STRATEGIC CONTROL PLACEMENT
    # Use attack path data to place controls where they actually protect
    controls_placed = set()

    # Get attack paths from ground truth for intelligent placement
    attack_paths = ground_truth.get('expected_attack_paths', [])

    # Build entry_point -> first_hop mapping for inline controls
    entry_to_first_hop = {}
    for path in attack_paths:
        entry = path.get('entry')
        path_nodes = path.get('path', [])
        if entry and len(path_nodes) > 1:
            # path[0] is entry itself, path[1] is first internal hop
            if entry == path_nodes[0] and len(path_nodes) > 1:
                entry_to_first_hop[entry] = path_nodes[1]

    logger.info(f"Entry points found: {list(entry_to_first_hop.keys())}")

    # 1. MFA/Authentication Controls: Place on ALL entry points they protect
    # Check which attack paths the control addresses
    for control in ['mfa', 'sso', 'iam', 'authentication']:
        if control not in control_nodes:
            continue

        control_id = control_nodes[control]
        control_rec = next((r for r in control_recommendations if r.get('control') == control), None)

        if not control_rec:
            continue

        # Get attack paths this control addresses
        control_attack_paths = control_rec.get('attack_paths', [])
        placed_on_entries = set()

        for path_idx in control_attack_paths:
            if path_idx < len(attack_paths):
                path = attack_paths[path_idx]
                entry = path.get('entry')

                # Place MFA between entry and first hop
                if entry and entry in entry_to_first_hop and entry not in placed_on_entries:
                    first_hop = entry_to_first_hop[entry]
                    after_lines.append(f"    {entry} --> {control_id}")
                    after_lines.append(f"    {control_id} --> {first_hop}")
                    placed_on_entries.add(entry)
                    logger.info(f"Placed {control} on entry: {entry} -> {first_hop}")

        if placed_on_entries:
            controls_placed.add(control)
            logger.info(f"MFA placed on {len(placed_on_entries)} entry points: {placed_on_entries}")

    # 2. WAF/Firewall/DDoS: Between Internet-like entries and first component
    for control in ['waf', 'firewall', 'ddos protection']:
        if control in control_nodes and internet_like:
            control_id = control_nodes[control]
            # Find what Internet-like nodes connect to
            placed_for_control = False
            for src_node in internet_like[:1]:  # Use first internet-like node
                if src_node in entry_to_first_hop:
                    first_hop = entry_to_first_hop[src_node]
                    after_lines.append(f"    {src_node} --> {control_id}")
                    after_lines.append(f"    {control_id} --> {first_hop}")
                    controls_placed.add(control)
                    placed_for_control = True
                    break

            # Fallback to old logic if no path data
            if not placed_for_control:
                for (src, dst), edge_line in edge_dict.items():
                    if src in internet_like:
                        after_lines.append(f"    {src} --> {control_id}")
                        after_lines.append(f"    {control_id} --> {dst}")
                        controls_placed.add(control)
                        break

    # 3. Backup/Replication: Connected to database (recovery layer)
    for control in ['backup', 'database replication', 'encryption at rest']:
        if control in control_nodes and db_like:
            control_id = control_nodes[control]
            # Connect to ALL persistent databases (not volatile caches)
            for db_node in db_like:
                # Skip volatile caches for backup/replication
                if control in ['backup', 'database replication'] and 'cache' in db_node.lower():
                    continue
                after_lines.append(f"    {db_node} -.->|protected by| {control_id}")
            controls_placed.add(control)

    # 4. Logging/SIEM/Monitoring: Connected to multiple components (detection layer)
    for control in ['logging', 'siem', 'audit log', 'monitoring']:
        if control in control_nodes:
            control_id = control_nodes[control]
            # Connect to key components (prefer app layer first, then data layer)
            if all_app_nodes:
                after_lines.append(f"    {all_app_nodes[0]} -.->|logs to| {control_id}")
            # Connect to ALL databases for audit logging
            for db_node in db_like:
                after_lines.append(f"    {db_node} -.->|audits to| {control_id}")
            controls_placed.add(control)
            break  # Only add one monitoring control

    # 5. Rate limiting/Input validation: At application layer (prevention)
    for control in ['rate limiting', 'input validation', 'api gateway']:
        if control in control_nodes and (web_like or all_app_nodes):
            control_id = control_nodes[control]
            target = web_like[0] if web_like else all_app_nodes[0]
            # Place before the application node
            if internet_like:
                after_lines.append(f"    {internet_like[0]} --> {control_id}")
                after_lines.append(f"    {control_id} --> {target}")
            else:
                after_lines.append(f"    {control_id} --> {target}")
            controls_placed.add(control)

    # 6. CDN: At perimeter, before Internet entry
    if 'cdn' in control_nodes and internet_like:
        control_id = control_nodes['cdn']
        # CDN sits at edge, before internet entry reaches architecture
        if internet_like and internet_like[0] in entry_to_first_hop:
            first_hop = entry_to_first_hop[internet_like[0]]
            after_lines.append(f"    {control_id} --> {internet_like[0]}")
            after_lines.append(f"    %% CDN caches content at edge, protects from DDoS")
        else:
            after_lines.append(f"    {control_id} -.->|edge protection| {internet_like[0]}")
        controls_placed.add('cdn')

    # 7. Load Balancer: Between perimeter and application layer
    if 'load balancer' in control_nodes:
        control_id = control_nodes['load balancer']
        if web_like:
            # Check if there's already a LoadBalancer node in architecture
            has_lb_node = any('loadbalancer' in line.lower() or 'load balancer' in line.lower()
                            for line in structure_lines)
            if not has_lb_node and internet_like and web_like:
                # Place between perimeter and web tier
                after_lines.append(f"    {internet_like[0]} --> {control_id}")
                after_lines.append(f"    {control_id} --> {web_like[0]}")
            else:
                # Already exists or unclear topology, show as protecting web tier
                after_lines.append(f"    {control_id} -.->|balances load to| {web_like[0]}")
        controls_placed.add('load balancer')

    # 8. IDS/IPS: Network monitoring at perimeter or between segments
    for control in ['ids', 'ips', 'ids/ips', 'intrusion detection']:
        if control in control_nodes:
            control_id = control_nodes[control]
            # IDS monitors network traffic passively
            if internet_like and web_like:
                after_lines.append(f"    {control_id} -.->|monitors| {internet_like[0]}")
                after_lines.append(f"    {control_id} -.->|monitors| {web_like[0]}")
            elif all_app_nodes:
                after_lines.append(f"    {control_id} -.->|monitors network| {all_app_nodes[0]}")
            controls_placed.add(control)

    # 9. EDR: Endpoint detection and response on servers
    for control in ['edr', 'endpoint detection', 'antivirus']:
        if control in control_nodes:
            control_id = control_nodes[control]
            # EDR runs on endpoints (application servers, databases)
            nodes_to_protect = []
            if all_app_nodes:
                nodes_to_protect.extend(all_app_nodes[:2])  # First 2 app nodes
            if db_like:
                nodes_to_protect.append(db_like[0])

            for node in nodes_to_protect[:3]:  # Max 3 connections to avoid clutter
                after_lines.append(f"    {node} -.->|protected by| {control_id}")
            controls_placed.add(control)

    # 10. DLP: Data loss prevention at data layer
    for control in ['dlp', 'data loss prevention']:
        if control in control_nodes and db_like:
            control_id = control_nodes[control]
            # DLP monitors ALL databases for data access and exfiltration
            for db_node in db_like:
                after_lines.append(f"    {db_node} -.->|monitored by| {control_id}")
            controls_placed.add(control)

    # 11. Web Content Filtering: At application/web layer
    if 'web content filtering' in control_nodes and web_like:
        control_id = control_nodes['web content filtering']
        after_lines.append(f"    {web_like[0]} -.->|filtered by| {control_id}")
        controls_placed.add('web content filtering')

    # 12. Email Gateway: Protects against phishing at user entry
    for control in ['email gateway', 'email filtering', 'anti-phishing']:
        if control in control_nodes:
            control_id = control_nodes[control]
            # Email gateway sits before users/internal systems
            if all_app_nodes:
                after_lines.append(f"    {control_id} -.->|filters email to| {all_app_nodes[0]}")
            controls_placed.add(control)

    # 13. AI-specific controls: Use placement data from enrichment
    # Check for AI/ML controls with placement information
    ai_control_keywords = [
        'output_filtering', 'content_moderation', 'sandbox', 'pii_detection',
        'prompt_filtering', 'input_validation', 'context_grounding', 'rag_verification',
        'human_in_loop', 'tool_allowlist', 'differential_privacy', 'anonymization',
        'data_minimization', 'capability_restrictions', 'api_key_rotation',
        'secrets_management', 'model_monitoring'
    ]

    for control_kw in ai_control_keywords:
        if control_kw not in control_nodes:
            continue

        # Skip if already placed by hardcoded sections
        if control_kw in controls_placed:
            continue

        control_id = control_nodes[control_kw]
        control_rec = next((r for r in control_recommendations
                           if r.get('control') == control_kw and 'AI/ML' in r.get('rationale', '')), None)

        if not control_rec:
            continue

        # Get placement from enriched control data
        placement = control_rec.get('placement', '')

        # Extract node name from placement (e.g., "At AgentOrchestrator hop" -> "AgentOrchestrator")
        placed_at_node = None
        if placement and 'At ' in placement and ' hop' in placement:
            # Extract node name between "At " and " hop"
            node_part = placement.split('At ')[1].split(' hop')[0].strip()
            # Try to find matching node ID (case-insensitive, handle spaces)
            node_part_normalized = node_part.replace(' ', '').lower()

            # Search for matching node in structure
            for node_line in structure_lines:
                for part in node_line.split():
                    if any(c in part for c in ['(', '[', '{']):
                        node_id = part.split('(')[0].split('[')[0].split('{')[0]
                        if node_id.lower().replace('_', '') == node_part_normalized:
                            placed_at_node = node_id
                            break
                if placed_at_node:
                    break

        # Connect control to its placement node
        if placed_at_node:
            dir_category = control_rec.get('dir_category', 'prevention')
            if dir_category == 'prevention':
                after_lines.append(f"    {control_id} --> {placed_at_node}")
            else:
                after_lines.append(f"    {placed_at_node} -.->|{dir_category}| {control_id}")
            controls_placed.add(control_kw)
            logger.info(f"Placed AI control {control_kw} at {placed_at_node} ({dir_category})")
        else:
            # Fallback: Look for AI-related nodes
            ai_nodes = [n for n in all_app_nodes if any(kw in structure_lines[i].lower()
                       for i, line in enumerate(structure_lines)
                       for kw in ['llm', 'agent', 'prompt', 'ai', 'model', 'vector', 'orchestrat', 'tool']
                       if n in line)]
            if ai_nodes:
                after_lines.append(f"    {control_id} --> {ai_nodes[0]}")
                controls_placed.add(control_kw)
                logger.info(f"Placed AI control {control_kw} at fallback node {ai_nodes[0]}")
            elif all_app_nodes:
                after_lines.append(f"    {control_id} --> {all_app_nodes[0]}")
                controls_placed.add(control_kw)
                logger.info(f"Placed AI control {control_kw} at fallback node {all_app_nodes[0]}")

    # 14. Network segmentation/Zero Trust: Shown as protecting perimeter or data layer
    for control in ['network segmentation', 'zero trust', 'micro-segmentation']:
        if control in control_nodes:
            control_id = control_nodes[control]
            # Connect between layers to show isolation
            if db_like and all_app_nodes:
                after_lines.append(f"    {control_id} -.->|isolates| {db_like[0]}")
                after_lines.append(f"    {control_id} -.->|isolates| {all_app_nodes[0]}")
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

    # 15. Fallback: Place any remaining controls using their placement data
    all_control_names = [rec.get("control") if isinstance(rec, dict) else rec for rec in control_recommendations]
    unplaced_controls = [name for name in all_control_names if name in control_nodes and name not in controls_placed]

    for control_name in unplaced_controls:
        control_id = control_nodes[control_name]
        control_rec = next((r for r in control_recommendations if r.get('control') == control_name), None)

        if not control_rec:
            continue

        # Try to use placement data
        placement = control_rec.get('placement', '')
        placed = False

        if placement and 'At ' in placement and ' hop' in placement:
            # Extract node name
            node_part = placement.split('At ')[1].split(' hop')[0].strip()
            node_part_normalized = node_part.replace(' ', '').replace('/', '').lower()

            # Find matching node
            for node_line in structure_lines:
                for part in node_line.split():
                    if any(c in part for c in ['(', '[', '{']):
                        node_id = part.split('(')[0].split('[')[0].split('{')[0]
                        node_normalized = node_id.lower().replace('_', '').replace('/', '')
                        # More flexible matching
                        if node_normalized in node_part_normalized or node_part_normalized in node_normalized:
                            dir_category = control_rec.get('dir_category', 'prevention')
                            if dir_category == 'prevention':
                                after_lines.append(f"    {control_id} --> {node_id}")
                            else:
                                after_lines.append(f"    {node_id} -.->|{dir_category}| {control_id}")
                            controls_placed.add(control_name)
                            placed = True
                            logger.info(f"Fallback placed {control_name} at {node_id}")
                            break
                if placed:
                    break

        # If still not placed, use generic fallback
        if not placed:
            dir_category = control_rec.get('dir_category', 'prevention')
            layer = control_rec.get('layer', 'application')

            # Choose target based on layer
            targets = []
            if layer == 'data' and db_like:
                # For data layer controls, place on ALL databases
                targets = db_like
            elif layer == 'identity' and web_like:
                targets = [web_like[0]]
            elif web_like:
                targets = [web_like[0]]
            elif all_app_nodes:
                targets = [all_app_nodes[0]]
            else:
                continue  # Can't place

            for target in targets:
                if dir_category == 'prevention':
                    after_lines.append(f"    {control_id} --> {target}")
                else:
                    after_lines.append(f"    {target} -.->|{dir_category}| {control_id}")
            controls_placed.add(control_name)
            logger.info(f"Generic fallback placed {control_name} at {len(targets)} node(s) ({layer} layer)")

    # 9. Add original architecture edges (after control placements)
    after_lines.append("")
    after_lines.append("    %% ORIGINAL ARCHITECTURE EDGES (below)")
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


def generate_threat_model_report(ground_truth: Dict) -> str:
    """
    Generate 09_threat_model.md.

    Structured as a decision-maker narrative: overview of what is at risk and why,
    per attack path with threat actor / exploited vulnerability / business impact,
    and a clear bridge to the ADR and Action Plan for next steps.
    """
    tm = ground_truth.get("threat_model", {})
    attack_paths = ground_truth.get("expected_attack_paths", [])
    rr_summary = tm.get("residual_risk_summary", {})
    blackhat = ground_truth.get("blackhat_critique", {})
    arch_name = ground_truth.get("architecture", "this architecture")
    rapids = ground_truth.get("rapids_assessment", {})

    ob = rr_summary.get("overall_before", 0)
    oa = rr_summary.get("overall_after_controls", 0)
    pct = rr_summary.get("risk_reduction_pct", 0)
    status = rr_summary.get("status_after", "MONITOR")
    weakness = tm.get("architecture_weakness", "unknown")
    primary_actor = tm.get("primary_threat_actor", "Unknown threat actor")
    trust_boundaries = tm.get("trust_boundaries_at_risk", [])
    tier_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}

    lines = [f"# Threat Model — {arch_name}\n"]

    # --- Overview: one narrative block ---
    lines.append("## Overview\n")

    # RAPIDS threat summary sentence — fallback to per_threat initial_risk if risk_score is null
    per_threat_before = ground_truth.get("residual_risks_before", {}).get("per_threat", {})
    scored_threats = sorted(
        [
            (
                cat,
                int(
                    (v.get("risk_score") if v.get("risk_score") is not None
                     else per_threat_before.get(cat, {}).get("initial_risk", 0))
                    or 0
                ),
            )
            for cat, v in rapids.items()
            if isinstance(v, dict) and cat != "_metadata"
        ],
        key=lambda x: x[1], reverse=True,
    )
    scored_threats = [(cat, score) for cat, score in scored_threats if score > 0]
    top_threat_strs = [f"{cat.replace('_', ' ').title()} ({score}/100)" for cat, score in scored_threats[:3]]
    rapids_sentence = (
        f"The dominant threat categories are {', '.join(top_threat_strs)}."
        if top_threat_strs else ""
    )

    # How many APs and what tier
    crit_count = sum(1 for ap in attack_paths if ap.get("criticality_tier") == "CRITICAL")
    ap_sentence = (
        f"{len(attack_paths)} attack path(s) identified, "
        f"{crit_count} CRITICAL."
        if attack_paths else "No attack paths identified."
    )

    # Bottleneck and trust boundary sentence
    tb_sentence = ""
    if trust_boundaries:
        tb_sentence = (
            f"`{weakness}` is the architectural bottleneck — present on most paths. "
            f"Nodes `{'`, `'.join(trust_boundaries)}` carry traffic across multiple paths "
            f"with no detection control, making them invisible pivot points for an attacker."
        )
    else:
        tb_sentence = f"`{weakness}` is the architectural bottleneck — present on most paths."

    lines.append(
        f"{ap_sentence} {rapids_sentence} "
        f"The primary threat actor is **{primary_actor}**. "
        f"{tb_sentence}\n"
    )
    lines.append(
        f"With all recommended controls applied, overall risk reduces from "
        f"**{ob}** to **{oa}/100** (−{pct}%, status: **{status}**). "
        f"The decisions behind each control placement are in the "
        f"[Architecture Decision Records](10_adr_report.md). "
        f"The implementation schedule is in the [Action Plan](03_action_plan.md).\n"
    )

    # --- Per-AP sections ---
    lines.append("---\n")

    # Journey coverage summary
    all_journeys = ground_truth.get("user_stories", {}).get("journeys", [])
    if all_journeys:
        corr_n = sum(1 for j in all_journeys if not j.get("no_user_story"))
        atk_n  = sum(1 for j in all_journeys if j.get("no_user_story"))
        lines.append(
            f"**User journey coverage:** {corr_n}/{len(all_journeys)} attack paths are corroborated "
            f"by a real user workflow."
        )
        if atk_n:
            lines.append(
                f" {atk_n} path{'s' if atk_n > 1 else ''} are post-compromise only — "
                f"no user baseline, detection requires network-layer controls."
            )
        lines.append("\n")

    sorted_aps = sorted(
        attack_paths,
        key=lambda ap: tier_order.get(ap.get("criticality_tier", "LOW"), 0),
        reverse=True,
    )

    for ap in sorted_aps:
        ap_id = ap.get("id", "?")
        tier = ap.get("criticality_tier", "UNKNOWN")
        path_str = " → ".join(ap.get("path", [ap.get("entry", "?"), ap.get("target", "?")]))
        rs = ap.get("risk_scenario", {})
        adr_ids = ap.get("adr_ids", [])

        lines.append(f"## {ap_id} [{tier}]: {path_str}\n")

        if rs:
            # Render as a mini-narrative, not a field list
            threat_actor = rs.get("threat_actor", "?")
            targeted_asset = rs.get("targeted_asset", "?")
            vuln = rs.get("exploited_vulnerability", "?")
            impact = rs.get("impact", "?")
            lines.append(
                f"**{threat_actor}** targets **{targeted_asset}** "
                f"by exploiting **{vuln}**. "
                f"If the path is not interrupted, the consequence is: {impact}.\n"
            )

            apt_ev = rs.get("apt_evidence", {})
            if apt_ev.get("top_group"):
                lines.append(f"**Known APT attribution:** {apt_ev['top_group']}\n")

            cves = rs.get("cve_ids", [])
            if cves:
                lines.append(f"**Associated CVEs:** {', '.join(cves[:3])}\n")

        # User Journey context
        journey_by_ap = {
            j.get("attack_path_id"): j
            for j in ground_truth.get("user_stories", {}).get("journeys", [])
            if j.get("attack_path_id")
        }
        j = journey_by_ap.get(ap_id)
        if j and not j.get("no_user_story"):
            role = j.get("user_role", "user")
            lines.append(f"**User journey context:** {j.get('story_text', '')}\n")
            exploit_chain = j.get("exploitation_chain", "")
            if exploit_chain:
                lines.append(f"**Exploitation chain:** {exploit_chain}\n")
            lines.append(
                f"> Detection note: a real {role} follows this exact path in normal use. "
                f"The attacker blends with legitimate traffic — behavioural anomaly detection "
                f"can help but thresholds must be precise.\n"
            )
        elif j and j.get("no_user_story"):
            lines.append(
                f"> **Post-compromise path:** No normal user follows this route. "
                f"An attacker must already have a foothold before reaching this path. "
                f"Detection must rely on network segmentation or explicit hop-level monitoring — "
                f"not user behavioural baselines.\n"
            )

        # ATLAS AI-specific techniques — surface in narrative if present on this path
        ap_techs = ap.get("techniques", [])
        atlas_on_path = [t for t in ap_techs if t.startswith("AML.")]
        if atlas_on_path:
            try:
                from chatbot.modules.atlas_helper import get_atlas_helper
                _atlas = get_atlas_helper()
            except Exception:
                _atlas = None
            atlas_names = []
            for tid in atlas_on_path:
                t = _atlas.get_technique_by_id(tid) if _atlas else None
                atlas_names.append(f"{tid} ({t.get('name', tid)})" if t else tid)
            lines.append(
                f"**AI-specific threats (MITRE ATLAS):** This path also exposes AI/ML-layer "
                f"attack vectors: {', '.join(atlas_names)}. "
                f"These are distinct from traditional MITRE ATT&CK techniques — they target "
                f"the model, prompt interface, or inference API directly. "
                f"Standard network and endpoint controls do not address these vectors; "
                f"AI-specific controls (prompt filtering, output guardrails, RAG content validation, "
                f"API access scoping) are required.\n"
            )

        # Per-AP residual + ADR link
        per_ap = next(
            (r for r in rr_summary.get("per_ap_residual", []) if r.get("ap_id") == ap_id),
            {},
        )
        ap_residual = per_ap.get("residual_after_adrs", oa)
        if adr_ids:
            adr_links = ", ".join(f"[{a}](10_adr_report.md#{a.lower()})" for a in adr_ids)
            lines.append(
                f"**Residual risk after controls:** {ap_residual}/100  "
                f"**Decision record:** {adr_links}\n"
            )
        lines.append("")

    # --- Blackhat section ---
    if blackhat:
        lines.append("---\n")
        lines.append("## Cross-Path Chain Analysis (Blackhat)\n")
        chains = blackhat.get("chained_exploit_findings", [])
        stealth = blackhat.get("stealth_score", 0)
        stealthy_techs = blackhat.get("stealthy_techniques", [])
        gaps = blackhat.get("mitigation_gaps_for_chains", [])

        lines.append(
            f"The Blackhat critic analysed all paths together for chain-exploitation risk. "
            f"Stealth score: **{stealth}/100** "
            f"({'high — attacker can operate without triggering detection' if stealth >= 60 else 'moderate' if stealth >= 30 else 'low'}).\n"
        )
        if chains:
            lines.append(f"**Chained exploits identified ({len(chains)}):**\n")
            for c in chains[:5]:
                lines.append(f"- {c}")
            lines.append("")
        if stealthy_techs:
            lines.append(f"**Stealthy techniques:** {', '.join(stealthy_techs)}\n")
        if gaps:
            lines.append(f"**Cross-path mitigation gaps:**\n")
            for g in gaps[:5]:
                lines.append(f"- {g}")
            lines.append("")

    return "\n".join(lines)


def generate_adr_report(ground_truth: Dict) -> str:
    """
    Generate 10_adr_report.md — one master ADR per attack path.

    Narrative-first: context reads as a decision story (what threat, what gap,
    why these controls) rather than field dumps. Each ADR groups controls by hop.
    Links back to 09_threat_model.md and forward to 03_action_plan.md.
    """
    adrs = ground_truth.get("architecture_decision_records", [])
    arch_name = ground_truth.get("architecture", "this architecture")

    if not adrs:
        return "# Architecture Decision Records\n\n_No ADRs generated (no attack paths found)._\n"

    out = ["# Architecture Decision Records\n"]
    out.append(
        f"This document records the security decisions made for each attack path identified "
        f"in {arch_name}. Each ADR explains **what threat is being addressed**, "
        f"**where on the path each control is placed**, and **why that placement reduces risk**. "
        f"Controls are prioritised by RAPIDS threat score — the same scoring used in the "
        f"[Threat Model](09_threat_model.md). MITRE technique evidence and control confidence scores "
        f"are in the [Technical Report](02_technical_report.md). "
        f"Implementation sequencing is in the [Action Plan](03_action_plan.md).\n"
    )
    out.append(f"_{len(adrs)} decision record(s) — one per identified attack path._\n")
    out.append("\n---\n")

    for adr in adrs:
        adr_id = adr.get("adr_id", "ADR-?")
        ap_id = adr.get("attack_path_id", "?")
        tier = adr.get("attack_path_tier", "UNKNOWN")
        path_str = adr.get("attack_path", "?")
        status = adr.get("status", "proposed").upper()
        ctx = adr.get("context", {})
        con = adr.get("consequences", {})
        hops: List[Dict] = adr.get("hops", [])
        active_threats = ctx.get("active_threats", [])

        out.append(f"## {adr_id} — {ap_id} [{tier}]\n")
        out.append(f"**Path:** {path_str}  ")
        out.append(f"**Status:** {status}\n")

        # --- User Journey context (who legitimately uses this path) ---
        journey_by_ap = {
            j.get("attack_path_id"): j
            for j in ground_truth.get("user_stories", {}).get("journeys", [])
            if j.get("attack_path_id")
        }
        j = journey_by_ap.get(ap_id)
        if j and not j.get("no_user_story"):
            role = j.get("user_role", "user")
            out.append(f"\n### Who uses this path legitimately\n")
            out.append(f"{j.get('story_text', '')}\n")
            out.append(
                f"> This means the attacker's activity blends with real {role} traffic. "
                f"Controls on this path should combine **prevention** (stops the attack) "
                f"with **detection** calibrated to the {role} baseline.\n"
            )
        elif j and j.get("no_user_story"):
            out.append(f"\n### Who uses this path legitimately\n")
            out.append(
                f"No legitimate user follows this path in normal operation. "
                f"This path only makes sense as a post-compromise pivot — "
                f"an attacker already inside the network moving deeper.\n"
            )
            out.append(
                f"> Controls on this path should prioritise **network segmentation** "
                f"and **explicit hop monitoring** over behavioural anomaly detection.\n"
            )

        # --- Threat Scenario (narrative paragraph) ---
        out.append("\n### What is at risk\n")
        threat_scenario = ctx.get("threat_scenario", "")
        if threat_scenario:
            out.append(f"{threat_scenario}\n")

        # RAPIDS threat table — show what categories are active and their consequence
        if active_threats:
            out.append("\n**Active threat categories on this path:**\n")
            out.append("| Threat | Score | If exploited |")
            out.append("|--------|-------|-------------|")
            for t in active_threats[:5]:
                score = t.get("score", 0)
                cat = t.get("category", "").replace("_", " ").title()
                consequence = t.get("consequence", "—")
                out.append(f"| {cat} | {score}/100 | {consequence} |")
            out.append("")

        # --- Gap summary ---
        gap_summary = ctx.get("gap_summary", "")
        if gap_summary and gap_summary != "All hops are covered with at least one control.":
            out.append(f"\n> ⚠️ **Current gaps:** {gap_summary}\n")

        # --- Decision rationale ---
        decision_rationale = ctx.get("decision_rationale", "")
        if decision_rationale:
            out.append(f"\n**Why these controls:** {decision_rationale}\n")

        # --- Risk outcome ---
        ob = con.get("overall_risk_before", "?")
        oa = con.get("overall_risk_after", "?")
        pct = con.get("risk_reduction_pct", "?")
        new_risks = con.get("new_risks_introduced", [])
        out.append(f"\n**Risk outcome:** {ob} → {oa}/100 (−{pct}% reduction)\n")
        for r in new_risks:
            out.append(f"> ⚠️ **Residual gap:** {r}\n")

        # --- Hop-by-hop decisions ---
        out.append("\n### Control decisions by hop\n")
        out.append(
            "_Each hop is listed in traversal order. "
            "Controls are placed at the node where the attacker's technique is exercised. "
            "Hops with no control are flagged as gaps._\n"
        )

        for hop in hops:
            node = hop.get("node", "?")
            node_techs = hop.get("node_techniques", [])
            controls = hop.get("controls", [])
            gap_note = hop.get("gap_note")
            gap_type = hop.get("gap_type")

            tech_str = ", ".join(node_techs[:4]) if node_techs else "no techniques mapped"
            out.append(f"#### `{node}` — techniques: {tech_str}\n")

            if gap_note:
                _GAP_LABEL = {
                    "upstream_covered": "ℹ️ UPSTREAM COVERAGE ASSUMED",
                    "library_gap":      "⚠️ PATTERN LIBRARY GAP",
                    "detection_only":   "⚠️ DETECTION GAP",
                    "unmitigated":      "🔴 UNMITIGATED",
                }
                label = _GAP_LABEL.get(gap_type, "⚠️ GAP")
                out.append(f"> **{label}:** {gap_note}\n")

            if not controls:
                if gap_type == "upstream_covered":
                    out.append("_Techniques are assumed mitigated by upstream controls on this path._\n")
                elif gap_type == "library_gap":
                    out.append("_No control in the pattern library targets these techniques at this hop. MoE review required._\n")
                else:
                    out.append("_No control assigned to this hop — see gap note above._\n")
            else:
                for ctrl in controls:
                    priority = ctrl.get("priority", "medium").upper()
                    cat = ctrl.get("dir_category", "?").title()
                    rb = ctrl.get("risk_before", "?")
                    ra = ctrl.get("risk_after", "?")
                    red = ctrl.get("risk_reduction", "?")
                    out.append(f"**{ctrl['control'].title()}** [{priority}] — {cat}")
                    out.append(f"> {ctrl['reason']}")
                    out.append(f"> Risk: {rb} → {ra} (−{red} pts)\n")

        out.append(f"\n_Next step: see [Action Plan](03_action_plan.md) for implementation sequencing._\n")
        out.append("\n---\n")

    # ── ScrumMaster ADR section (appended when SM ran) ────────────────────
    sm_plan = ground_truth.get("scrum_master_action_plan", [])
    sm_redesign = ground_truth.get("scrum_master_redesign_signal", False)
    sm_retriggered = ground_truth.get("scrum_master_critics_retriggered", [])

    if sm_plan or sm_redesign:
        out.append("\n## 🧩 ScrumMaster — Cross-ADR Actions\n")
        sm_note = ground_truth.get("scrum_master_synthesis_note", "")
        if sm_note:
            out.append(f"> {sm_note}\n")
        if sm_retriggered:
            out.append(f"\nCritics re-triggered by ScrumMaster: {', '.join(sm_retriggered)}\n")
        if sm_redesign:
            out.append("\n> ⚠ **Architectural Redesign Recommended.** The following items "
                       "cannot be addressed through incremental controls alone. "
                       "They require structural changes to the architecture.\n")

        if sm_plan:
            out.append("\nThese actions span multiple ADRs and were identified after cross-critic "
                       "impediment analysis. They complement — not replace — the per-path ADRs above.\n")
            prio_labels = {"critical": "CRITICAL", "high": "HIGH", "medium": "MEDIUM", "low": "LOW"}
            for i, item in enumerate(sm_plan, 1):
                prio = item.get("priority", "medium").lower()
                label = prio_labels.get(prio, prio.upper())
                status = "OPEN — REDESIGN REQUIRED" if sm_redesign else "OPEN"
                out.append(f"\n### SM-ADR-{i:02d} [{label}] — {item.get('action', 'Action')}\n")
                out.append(f"**Status:** {status}  ")
                out.append(f"**Source:** ScrumMaster harmony synthesis\n")
                if item.get("rationale"):
                    out.append(f"\n**Context:** {item['rationale']}\n")
                if item.get("risk_reduction_estimate"):
                    out.append(f"\n**Expected risk reduction:** {item['risk_reduction_estimate']}  ")
                if item.get("effort"):
                    out.append(f"**Effort:** {item['effort']}\n")
                out.append(f"\n_See [Action Plan §ScrumMaster](03_action_plan.md) for implementation sequence._\n")

        out.append("\n---\n")

    return "\n".join(out)


def _mmd_safe(text: str, max_len: int = 40) -> str:
    """Sanitise text for use inside a Mermaid label string."""
    return text.replace('"', "'").replace('\n', ' ')[:max_len]


def _append_bh_subgraphs(base_mmd: str, bh: Dict) -> str:
    """
    Extend threatmodel_adr.mmd with BH cross-path chain subgraphs.

    One subgraph per least_resistance_path chain entry; pivot-node annotations
    outside subgraphs; stealth score summary node.  Called only when blackhat_critique
    is present so the base diagram is always clean without BH data.
    """
    from typing import List as _List  # local to avoid circular import guard
    chains = bh.get("least_resistance_paths", [])
    findings = bh.get("chained_exploit_findings", [])
    shared = bh.get("shared_nodes", {})
    stealth = bh.get("stealth_score", 0)
    stealth_techs = bh.get("stealthy_techniques", [])
    gaps = bh.get("mitigation_gaps_for_chains", [])

    if not chains and not findings:
        return base_mmd  # nothing to add

    lines = [
        "",
        "  %% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  %% ⚔️  BLACKHAT LAYER 2D — CROSS-PATH CHAIN SUBGRAPHS",
        "  %% Each subgraph = one chained exploit route BH found",
        "  %% ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
        "  classDef bhChain fill:#4a1942,stroke:#a855f7,color:#fff,font-size:9px",
        "  classDef bhGap   fill:#7c2d12,stroke:#f97316,color:#fff,font-size:9px,stroke-dasharray:4",
        "  classDef bhStealth fill:#1c1917,stroke:#78716c,color:#a8a29e,font-size:9px",
        "",
    ]

    # One subgraph per structured chain entry
    for ci, chain in enumerate(chains[:6]):
        if not isinstance(chain, dict):
            continue
        ap_chain = chain.get("chain", [])
        pivot    = chain.get("pivot", "?")
        crit     = chain.get("chain_criticality", "HIGH")
        if len(ap_chain) < 2:
            continue
        sg_id    = f"BHChain{ci}"
        src      = _mmd_safe(ap_chain[0], 12)
        dst      = _mmd_safe(ap_chain[1], 12)
        piv      = _mmd_safe(pivot, 15)
        lines.append(f'  subgraph {sg_id}["⚔️ BH Chain {ci+1} [{crit}]: {src} → {dst} via {piv}"]')
        lines.append(f'    direction LR')
        lines.append(f'    BHC{ci}SRC["{src}"]:::bhChain')
        lines.append(f'    BHC{ci}PIV["🔀 pivot: {piv}"]:::bhChain')
        lines.append(f'    BHC{ci}DST["{dst}"]:::bhChain')
        lines.append(f'    BHC{ci}SRC -.->|"chains to"| BHC{ci}PIV')
        lines.append(f'    BHC{ci}PIV -.->|"enables"| BHC{ci}DST')
        # Attach any matching gap
        if ci < len(gaps):
            gid = f"BHC{ci}GAP"
            lines.append(f'    {gid}["⚠ {_mmd_safe(gaps[ci], 40)}"]:::bhGap')
            lines.append(f'    {gid} -.->|"gap"| BHC{ci}PIV')
        lines.append(f'  end')
        lines.append("")

    # Fallback: use string findings if no structured chains
    if not chains and findings:
        lines.append(f'  subgraph BHFindings["⚔️ BH Chain Findings"]')
        lines.append(f'    direction LR')
        for fi, finding in enumerate(findings[:6]):
            fid = f"BHF{fi}"
            lines.append(f'    {fid}["{_mmd_safe(str(finding), 50)}"]:::bhChain')
            if fi > 0:
                lines.append(f'    BHF{fi-1} -.-> {fid}')
        lines.append(f'  end')
        lines.append("")

    # Stealth summary node
    if stealth > 0:
        tech_str = ", ".join(stealth_techs[:4]) if stealth_techs else "—"
        lines.append(f'  BHStealth["🕵️ Stealth: {stealth}/100 | {_mmd_safe(tech_str, 35)}"]:::bhStealth')
        lines.append("")

    return base_mmd.rstrip() + "\n" + "\n".join(lines) + "\n"


def generate_final_diagram(ground_truth: Dict) -> str:
    """
    Generate threatmodel_adr.mmd — one subgraph per attack path.

    Each subgraph shows:
    - The attack path as a node chain
    - A risk scenario note (actor / asset / technique / impact)
    - Per-hop control badges attached to the correct node (not all to first hop)
    - A gap badge on hops with no control (zero-trust: every hop must be verified)
    - Blackhat pivot annotations if available
    """
    attack_paths = ground_truth.get("expected_attack_paths", [])
    adrs = ground_truth.get("architecture_decision_records", [])
    blackhat = ground_truth.get("blackhat_critique", {})

    if not attack_paths:
        return "graph TB\n  note[\"No attack paths found\"]\n"

    # Index master ADRs by AP id
    adr_by_ap: Dict[str, Dict] = {
        adr.get("attack_path_id", ""): adr for adr in adrs
    }

    lines = ["graph LR"]
    lines.append("")
    lines.append("  %% Style definitions")
    lines.append("  classDef scenarioNote fill:#FF8C00,stroke:#c06000,color:#fff,font-size:10px")
    lines.append("  classDef controlNode fill:#1565C0,stroke:#0D47A1,color:#fff,font-size:9px")
    lines.append("  classDef gapNode fill:#B71C1C,stroke:#7F0000,color:#fff,font-size:9px,stroke-dasharray:4")
    lines.append("  classDef pivotNote fill:#6A1B9A,stroke:#4A148C,color:#fff,font-size:9px,stroke-dasharray:4")
    lines.append("  classDef critPath fill:#DC143C,stroke:#8B0000,color:#fff")
    lines.append("  classDef highPath fill:#E65100,stroke:#BF360C,color:#fff")
    lines.append("  classDef medPath  fill:#F57F17,stroke:#E65100,color:#000")
    lines.append("  classDef lowPath  fill:#2E7D32,stroke:#1B5E20,color:#fff")
    lines.append("")

    tier_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    tier_style = {"CRITICAL": "critPath", "HIGH": "highPath", "MEDIUM": "medPath", "LOW": "lowPath"}

    sorted_aps = sorted(
        attack_paths,
        key=lambda ap: tier_order.get(ap.get("criticality_tier", "LOW"), 0),
        reverse=True,
    )

    for ap in sorted_aps:
        ap_id = ap.get("id", "?")
        tier = ap.get("criticality_tier", "UNKNOWN")
        safe_ap = ap_id.replace("-", "")
        path_nodes: List[str] = ap.get("path", [])
        rs = ap.get("risk_scenario", {})
        node_style = tier_style.get(tier, "lowPath")

        # ── Subgraph header ──
        path_display = " → ".join(path_nodes)
        lines.append(f'  subgraph {safe_ap}["{ap_id} [{tier}]: {_mmd_safe(path_display, 60)}"]')
        lines.append(f'    direction LR')

        # ── Risk scenario note (one line per field, using <br/> for Mermaid) ──
        actor = _mmd_safe(rs.get("threat_actor", "Unknown actor").split("(")[0].strip(), 35)
        asset = _mmd_safe(rs.get("targeted_asset", "?").split("(")[0].strip(), 30)
        vuln  = _mmd_safe(rs.get("exploited_vulnerability", "?"), 35)
        impact = _mmd_safe(rs.get("impact", "?").split(";")[0].strip(), 35)
        scenario_label = (
            f"Actor: {actor}<br/>"
            f"Asset: {asset}<br/>"
            f"Via: {vuln}<br/>"
            f"Impact: {impact}"
        )
        lines.append(f'    SC{safe_ap}["{scenario_label}"]:::scenarioNote')
        lines.append("")

        # ── Path nodes ──
        node_ids: Dict[str, str] = {}
        prev_nid = None
        for ni, node in enumerate(path_nodes):
            nid = f"{safe_ap}N{ni}"
            node_ids[node] = nid
            lines.append(f'    {nid}["{_mmd_safe(node, 25)}"]:::{node_style}')
            if prev_nid:
                lines.append(f'    {prev_nid} --> {nid}')
            prev_nid = nid
        lines.append("")

        # ── Per-hop control and gap badges ──
        master_adr = adr_by_ap.get(ap_id)
        if master_adr:
            for hop in master_adr.get("hops", []):
                node = hop.get("node", "")
                nid = node_ids.get(node)
                if not nid:
                    continue

                gap_note = hop.get("gap_note")
                controls = hop.get("controls", [])

                # Gap badge
                if gap_note:
                    gap_id = f"{safe_ap}GAP{node.replace(' ','')}"
                    gap_short = _mmd_safe(gap_note, 70)
                    lines.append(f'    {gap_id}["⚠ {gap_short}"]:::gapNode')
                    lines.append(f'    {gap_id} -.->|"unprotected"| {nid}')

                # One badge per control (all shown — zero-trust: every hop matters)
                for ci, ctrl in enumerate(controls):
                    ctrl_id = f"{safe_ap}C{node.replace(' ','')}{ci}"
                    ctrl_name = _mmd_safe(ctrl["control"].title(), 22)
                    priority  = ctrl.get("priority", "medium").upper()[0]  # C/H/M/L
                    cat_short = ctrl.get("dir_category", "?")[:4].upper()
                    rb = ctrl.get("risk_before", "?")
                    ra = ctrl.get("risk_after", "?")
                    techs = ctrl.get("techniques_blocked", [])
                    tech_str = ", ".join(techs[:2]) if techs else "general"
                    label = f"{ctrl_name}<br/>[{priority}] {cat_short} | {rb}→{ra}<br/>blocks: {_mmd_safe(tech_str, 20)}"
                    lines.append(f'    {ctrl_id}["{label}"]:::controlNode')
                    lines.append(f'    {ctrl_id} -.->|"at {_mmd_safe(node, 15)}"| {nid}')

        lines.append(f'  end')
        lines.append("")

    # ── Blackhat pivot annotations (outside subgraphs) ──
    shared_nodes = blackhat.get("shared_nodes", {})
    for pivot_idx, (node, path_ids) in enumerate(list(shared_nodes.items())[:4]):
        pivot_id = f"Pivot{pivot_idx}"
        paths_str = _mmd_safe(", ".join(path_ids[:3]), 40)
        label = f"PIVOT: {_mmd_safe(node, 20)}<br/>shared: {paths_str}"
        lines.append(f'  {pivot_id}["{label}"]:::pivotNote')

    return "\n".join(lines) + "\n"


def generate_report_package(
    original_mmd_path: str,
    ground_truth: Dict,
    output_dir: str = "report"
) -> Dict[str, str]:
    """
    Generate complete report package with organized folder structure.

    Returns dict with paths to all generated files.
    """
    arch_name = Path(ground_truth.get("architecture", original_mmd_path)).stem
    report_base = Path(output_dir) / arch_name
    report_base.mkdir(parents=True, exist_ok=True)

    # --- Enrichment pipeline (deterministic, gated by settings) ---
    try:
        from chatbot.config.settings import get_settings
        settings = get_settings()
        cfg_narratives = settings.narratives
        cfg_adr = settings.adr
        cfg_tm = settings.threat_model

        if cfg_adr.enabled and "architecture_decision_records" not in ground_truth:
            from chatbot.modules.adr_generator import generate_adrs_from_ground_truth
            generate_adrs_from_ground_truth(ground_truth)

        if cfg_narratives.enabled:
            from chatbot.modules.narrative_enricher import enrich_ground_truth
            enrich_ground_truth(ground_truth)

        # APT attribution + CVE enrichment (additive — runs regardless of narrative flag)
        try:
            from chatbot.modules.threat_scene_deepener import deepen_threat_scenes
            from chatbot.modules.mitre import get_mitre_helper
            deepen_threat_scenes(ground_truth, get_mitre_helper())
        except Exception as _dep_exc:
            logger.warning(f"APT/CVE enrichment skipped: {_dep_exc}")

        if cfg_tm.enabled:
            from chatbot.modules.threat_model_builder import build_threat_model
            build_threat_model(ground_truth)

    except Exception as exc:
        logger.warning(f"Enrichment pipeline skipped due to error: {exc}")

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

    # --- TM / ADR / Final diagram (09 / 10 / 11) ---
    try:
        from chatbot.config.settings import get_settings
        settings = get_settings()
        if settings.threat_model.enabled and ground_truth.get("threat_model"):
            tm_report = generate_threat_model_report(ground_truth)
            paths["threat_model"] = save_report(tm_report, str(report_base / "09_threat_model.md"))

        if settings.adr.enabled and ground_truth.get("architecture_decision_records"):
            adr_report = generate_adr_report(ground_truth)
            paths["adr_report"] = save_report(adr_report, str(report_base / "10_adr_report.md"))

        if settings.threat_model.enabled and ground_truth.get("architecture_decision_records"):
            final_mmd = generate_final_diagram(ground_truth)
            paths["final_diagram"] = save_report(final_mmd, str(report_base / "threatmodel_adr.mmd"), "mmd")
            # BH variant: same diagram but with BH cross-path subgraphs appended (only when BH ran)
            if ground_truth.get("blackhat_critique"):
                bh_mmd = _append_bh_subgraphs(final_mmd, ground_truth["blackhat_critique"])
                paths["final_diagram_bh"] = save_report(bh_mmd, str(report_base / "threatmodel_adr_bh.mmd"), "mmd")

        # Re-save ground_truth.json with enriched fields
        paths["ground_truth"] = save_report(
            json.dumps(ground_truth, indent=2),
            str(report_base / "ground_truth.json"),
            "json"
        )
    except Exception as exc:
        logger.warning(f"09/10/11 generation skipped: {exc}")

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

    # Add RAPIDS summary (Phase 3B-2: Filter metadata)
    rapids = ground_truth['rapids_assessment']
    rapids_filtered = {k: v for k, v in rapids.items() if not k.startswith("_") and isinstance(v, dict) and "risk" in v}
    for category, scores in sorted(rapids_filtered.items(), key=lambda x: x[1]['risk'], reverse=True):
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
