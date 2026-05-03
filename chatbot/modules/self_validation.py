"""
Self-Validation Framework for Threat Modeling

Validates that:
1. MITRE techniques are actually relevant to attack paths
2. RAPIDS assessments align with detected controls/vulnerabilities
3. Control recommendations address the identified techniques
4. Confidence scores are justified by evidence

Self-checks increase confidence when validations pass, decrease when they fail.
This creates a feedback loop for continuous improvement.
"""

from typing import Dict, List, Tuple, Set
import logging
from collections import defaultdict

from chatbot.modules.mitre import MitreHelper

logger = logging.getLogger(__name__)


# ============================================================================
# VALIDATION 1: MITRE TECHNIQUE RELEVANCE
# ============================================================================

def validate_technique_for_path(
    technique_id: str,
    path: Dict,
    nodes: Dict[str, Dict],
    mitre: MitreHelper
) -> Tuple[bool, float, str]:
    """
    Validate that a MITRE technique is actually relevant to an attack path.

    Returns: (is_valid, confidence_adjustment, reason)
    """
    tech = mitre.find_technique(technique_id)
    if not tech:
        return (False, -0.2, f"Technique {technique_id} not found in MITRE")

    tech_name = tech.get('name', '').lower()
    tech_desc = tech.get('description', '').lower()

    path_nodes = path.get("path", [])
    entry_label = nodes[path_nodes[0]].get("label", "").lower() if path_nodes else ""
    target_label = nodes[path_nodes[-1]].get("label", "").lower() if len(path_nodes) > 1 else ""
    path_str = " → ".join([nodes[n].get("label", n) for n in path_nodes]).lower()

    # Validation rules by technique
    validations = []

    # T1190 - Exploit Public-Facing Application
    if technique_id == "T1190":
        has_internet_entry = any(kw in entry_label for kw in ["internet", "public", "external", "mobile"])
        has_web_component = any(kw in path_str for kw in ["web", "api", "server", "gateway", "load balancer"])

        if has_internet_entry and has_web_component:
            validations.append((True, 0.1, "Clear public-facing entry with web components"))
        elif has_internet_entry:
            validations.append((True, 0.05, "Public entry present but web components unclear"))
        else:
            validations.append((False, -0.1, "No clear public-facing entry point"))

    # T1078 - Valid Accounts
    elif technique_id == "T1078":
        has_auth_component = any(kw in path_str for kw in ["auth", "login", "user", "identity", "sso", "mfa"])
        has_credential_target = any(kw in target_label for kw in ["database", "user", "account", "credential"])

        if has_auth_component or has_credential_target:
            validations.append((True, 0.1, "Authentication/credential components present"))
        else:
            validations.append((False, -0.05, "No clear authentication context"))

    # T1213 - Data from Information Repositories
    elif technique_id == "T1213":
        has_data_target = any(kw in target_label for kw in ["database", "db", "storage", "data", "repository", "file"])

        if has_data_target:
            validations.append((True, 0.1, "Data repository target confirmed"))
        else:
            validations.append((False, -0.1, "Target is not a data repository"))

    # T1059 - Command and Scripting Interpreter
    elif technique_id == "T1059":
        has_exec_component = any(kw in path_str for kw in ["server", "application", "exec", "lambda", "function", "worker"])

        if has_exec_component:
            validations.append((True, 0.08, "Execution environment present"))
        else:
            validations.append((False, -0.05, "No execution environment detected"))

    # T1566 - Phishing
    elif technique_id == "T1566":
        has_user_entry = any(kw in entry_label for kw in ["user", "employee", "client", "mobile"])

        if has_user_entry:
            validations.append((True, 0.08, "User entry point for phishing vector"))
        else:
            validations.append((False, -0.1, "No user entry point for phishing"))

    # T1090 - Proxy
    elif technique_id == "T1090":
        has_intermediary = any(kw in path_str for kw in ["proxy", "gateway", "load balancer", "cdn", "router"])

        if has_intermediary:
            validations.append((True, 0.08, "Intermediary component detected"))
        else:
            validations.append((False, -0.05, "No proxy/intermediary component"))

    # Default: Check if technique name/description has keywords from path
    else:
        path_keywords = set(path_str.split())
        tech_keywords = set((tech_name + " " + tech_desc).split())
        overlap = len(path_keywords & tech_keywords)

        if overlap >= 3:
            validations.append((True, 0.05, f"Generic match ({overlap} keywords overlap)"))
        else:
            validations.append((False, 0.0, "Generic technique, no specific validation"))

    # Aggregate validations
    if not validations:
        return (True, 0.0, "No validation rules for this technique")

    passed = sum(1 for v in validations if v[0])
    total = len(validations)
    avg_adjustment = sum(v[1] for v in validations) / total
    reasons = "; ".join(v[2] for v in validations)

    is_valid = passed >= total * 0.5  # At least 50% rules pass

    return (is_valid, avg_adjustment, reasons)


# ============================================================================
# VALIDATION 2: RAPIDS RELEVANCE
# ============================================================================

def validate_rapids_assessment(
    rapids: Dict,
    controls_present: List[str],
    attack_paths: List[Dict],
    architecture_type: str
) -> Tuple[bool, List[str]]:
    """
    Validate that RAPIDS scores align with actual architecture state.

    Returns: (is_valid, issues_found)
    """
    issues = []
    controls_set = set(controls_present)

    # Validation 1: Ransomware risk should be high if no backup
    ransomware = rapids.get("ransomware", {})
    ransomware_risk = ransomware.get("risk", 0)
    has_backup = any(c in controls_set for c in ["backup", "database replication"])

    if ransomware_risk >= 70 and has_backup:
        issues.append("HIGH ransomware risk despite backup present - risk may be overestimated")
    elif ransomware_risk < 50 and not has_backup:
        issues.append("LOW ransomware risk despite no backup - risk may be underestimated")

    # Validation 2: Application vuln risk should be high if public-facing and no WAF
    app_vulns = rapids.get("application_vulns", {})
    app_vuln_risk = app_vulns.get("risk", 0)
    has_waf = "waf" in controls_set
    has_public_entry = any(
        any(kw in path.get("entry", "").lower() for kw in ["internet", "public", "external"])
        for path in attack_paths
    )

    if has_public_entry and not has_waf and app_vuln_risk < 60:
        issues.append("Public-facing with no WAF but app vuln risk < 60 - may be underestimated")
    elif not has_public_entry and app_vuln_risk >= 80:
        issues.append("No public entry but HIGH app vuln risk - may be overestimated")

    # Validation 3: AI-specific risks should be elevated for AI systems
    if architecture_type == "ai_system":
        if app_vuln_risk < 80:
            issues.append("AI system should have app_vuln risk >= 80 (prompt injection)")
        if rapids.get("dos", {}).get("risk", 0) < 70:
            issues.append("AI system should have DoS risk >= 70 (API abuse)")

    # Validation 4: IoT systems should have high DoS risk
    if architecture_type == "iot":
        if rapids.get("dos", {}).get("risk", 0) < 70:
            issues.append("IoT system should have DoS risk >= 70 (resource constraints)")

    is_valid = len(issues) == 0
    return (is_valid, issues)


# ============================================================================
# VALIDATION 3: CONTROL-TO-TECHNIQUE ALIGNMENT
# ============================================================================

def validate_control_addresses_technique(
    control: str,
    technique_id: str,
    mitigation_ids: List[str],
    mitre: MitreHelper
) -> Tuple[bool, float, str]:
    """
    Validate that a control actually addresses the claimed technique.

    Returns: (is_valid, confidence_boost, reason)
    """
    # Get technique's official mitigations
    official_mits = mitre.get_technique_mitigations(technique_id)
    official_mit_ids = set(m.get("mitigation_id") for m in official_mits)

    # Check overlap
    claimed_mits = set(mitigation_ids)
    overlap = claimed_mits & official_mit_ids

    if not overlap:
        return (False, -0.15, f"No overlap between claimed and official mitigations for {technique_id}")

    # Calculate overlap percentage
    overlap_pct = len(overlap) / len(official_mit_ids) if official_mit_ids else 0.0

    if overlap_pct >= 0.5:
        return (True, 0.15, f"Strong alignment: {len(overlap)}/{len(official_mit_ids)} official mitigations")
    elif overlap_pct >= 0.25:
        return (True, 0.08, f"Good alignment: {len(overlap)}/{len(official_mit_ids)} official mitigations")
    else:
        return (True, 0.03, f"Weak alignment: {len(overlap)}/{len(official_mit_ids)} official mitigations")


# ============================================================================
# OVERALL VALIDATION & CONFIDENCE ADJUSTMENT
# ============================================================================

def run_self_validation(
    ground_truth: Dict,
    nodes: Dict[str, Dict],
    architecture_type: str
) -> Dict:
    """
    Run all validation checks and adjust confidence scores.

    Returns: Validation report with adjusted confidence
    """
    mitre = MitreHelper(use_local=True)
    attack_paths = ground_truth.get("expected_attack_paths", [])
    rapids = ground_truth.get("rapids_assessment", {})
    controls_present = ground_truth.get("controls_present", [])
    control_recs = ground_truth.get("control_recommendations", [])

    validation_report = {
        "overall_valid": True,
        "validations": {
            "technique_relevance": [],
            "rapids_alignment": [],
            "control_technique_mapping": []
        },
        "confidence_adjustments": {},
        "issues_found": []
    }

    # Validation 1: Technique relevance for each path
    logger.info("=" * 80)
    logger.info("SELF-VALIDATION: Checking MITRE technique relevance...")
    logger.info("=" * 80)

    for path_idx, path in enumerate(attack_paths):
        techniques = path.get("techniques", [])
        for tech_id in techniques:
            is_valid, adjustment, reason = validate_technique_for_path(
                tech_id, path, nodes, mitre
            )

            validation_report["validations"]["technique_relevance"].append({
                "path_index": path_idx,
                "technique": tech_id,
                "valid": is_valid,
                "adjustment": adjustment,
                "reason": reason
            })

            if not is_valid:
                validation_report["overall_valid"] = False
                validation_report["issues_found"].append(f"Path #{path_idx+1}: {tech_id} - {reason}")
                logger.warning(f"  ⚠️  Path #{path_idx+1}: {tech_id} - {reason}")
            else:
                logger.info(f"  ✓ Path #{path_idx+1}: {tech_id} - {reason}")

    # Validation 2: RAPIDS alignment
    logger.info("")
    logger.info("SELF-VALIDATION: Checking RAPIDS assessment alignment...")
    logger.info("=" * 80)

    rapids_valid, rapids_issues = validate_rapids_assessment(
        rapids, controls_present, attack_paths, architecture_type
    )

    validation_report["validations"]["rapids_alignment"] = {
        "valid": rapids_valid,
        "issues": rapids_issues
    }

    if not rapids_valid:
        validation_report["overall_valid"] = False
        validation_report["issues_found"].extend(rapids_issues)
        for issue in rapids_issues:
            logger.warning(f"  ⚠️  {issue}")
    else:
        logger.info("  ✓ RAPIDS assessment aligns with architecture state")

    # Validation 3: Control-technique mappings
    logger.info("")
    logger.info("SELF-VALIDATION: Checking control-to-technique mappings...")
    logger.info("=" * 80)

    for rec in control_recs:
        control = rec["control"]
        techniques = rec.get("techniques", [])
        mitigations = rec.get("mitigations", [])

        control_adjustments = []

        for tech_id in techniques[:3]:  # Validate top 3 techniques
            is_valid, adjustment, reason = validate_control_addresses_technique(
                control, tech_id, mitigations, mitre
            )

            control_adjustments.append(adjustment)

            validation_report["validations"]["control_technique_mapping"].append({
                "control": control,
                "technique": tech_id,
                "valid": is_valid,
                "adjustment": adjustment,
                "reason": reason
            })

            if not is_valid:
                validation_report["overall_valid"] = False
                validation_report["issues_found"].append(f"{control} → {tech_id}: {reason}")
                logger.warning(f"  ⚠️  {control} → {tech_id}: {reason}")
            else:
                logger.info(f"  ✓ {control} → {tech_id}: {reason}")

        # Store average adjustment for this control
        if control_adjustments:
            avg_adjustment = sum(control_adjustments) / len(control_adjustments)
            validation_report["confidence_adjustments"][control] = avg_adjustment

    # Summary
    logger.info("")
    logger.info("=" * 80)
    logger.info("SELF-VALIDATION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Overall Valid: {'✓ PASS' if validation_report['overall_valid'] else '✗ FAIL'}")
    logger.info(f"Issues Found: {len(validation_report['issues_found'])}")

    if validation_report["issues_found"]:
        logger.info("")
        logger.info("Issues requiring attention:")
        for issue in validation_report["issues_found"]:
            logger.info(f"  • {issue}")

    # Log confidence adjustments
    if validation_report["confidence_adjustments"]:
        logger.info("")
        logger.info("Confidence adjustments recommended:")
        for control, adjustment in validation_report["confidence_adjustments"].items():
            sign = "+" if adjustment >= 0 else ""
            logger.info(f"  • {control}: {sign}{adjustment:.1%}")

    logger.info("=" * 80)

    return validation_report


def apply_confidence_adjustments(
    control_recommendations: List[Dict],
    validation_report: Dict
) -> List[Dict]:
    """
    Apply confidence adjustments from validation to control recommendations.
    """
    adjustments = validation_report.get("confidence_adjustments", {})

    adjusted_recs = []
    for rec in control_recommendations:
        control = rec["control"]

        if control in adjustments:
            adjustment = adjustments[control]
            old_conf = rec.get("confidence", {})
            old_score = old_conf.get("score", 0.0)

            new_score = max(0.0, min(1.0, old_score + adjustment))  # Clamp to [0, 1]

            # Update confidence level
            if new_score >= 0.80:
                new_level = "HIGH"
            elif new_score >= 0.60:
                new_level = "MEDIUM"
            else:
                new_level = "LOW"

            # Update recommendation
            rec["confidence"]["score"] = new_score
            rec["confidence"]["level"] = new_level
            rec["confidence"]["validation_adjustment"] = adjustment

            if adjustment != 0:
                logger.info(f"Adjusted {control}: {old_score:.0%} → {new_score:.0%} ({new_level})")

        adjusted_recs.append(rec)

    return adjusted_recs
