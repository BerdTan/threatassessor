"""
Threat-Driven Control Recommendation Engine

Generates control recommendations by:
1. Extracting MITRE techniques from attack paths
2. Looking up MITRE mitigations for those techniques
3. Mapping MITRE mitigations to implementable security controls
4. Prioritizing by attack path criticality and RAPIDS threat scores
5. Filtering out controls already present

This provides DEFENSIBLE, TRACEABLE recommendations backed by MITRE ATT&CK.
"""

from typing import Dict, List, Set, Tuple
import logging
from collections import defaultdict

from chatbot.modules.mitre import MitreHelper
from chatbot.modules.confidence_scoring import add_confidence_to_recommendations

logger = logging.getLogger(__name__)


# ============================================================================
# MITRE MITIGATION → SECURITY CONTROL MAPPING
# ============================================================================

# Map MITRE Mitigation IDs to implementable security controls
# Reference: https://attack.mitre.org/mitigations/enterprise/
MITIGATION_TO_CONTROLS = {
    "M1013": ["application isolation", "sandbox"],  # Application Developer Guidance
    "M1015": ["active directory hardening", "least privilege"],  # Active Directory Configuration
    "M1016": ["least privilege"],  # Privileged Account Management (deprecated, use M1026)
    "M1017": ["patching", "vulnerability scanning"],  # User Training
    "M1018": ["user account management", "least privilege"],  # User Account Management
    "M1019": ["threat intelligence"],  # Threat Intelligence Program
    "M1020": ["tls", "encryption in transit", "certificate pinning"],  # SSL/TLS Inspection
    "M1021": ["application whitelisting"],  # Restrict Web-Based Content
    "M1022": ["least privilege", "iam"],  # Restrict File and Directory Permissions
    "M1024": ["least privilege", "iam"],  # Restrict Registry Permissions
    "M1025": ["least privilege", "iam"],  # Privileged Process Integrity
    "M1026": ["least privilege", "iam", "rbac"],  # Privileged Account Management
    "M1027": ["patching", "vulnerability scanning"],  # Password Policies
    "M1028": ["os hardening", "host firewall"],  # Operating System Configuration
    "M1029": ["remote access controls", "vpn", "zero trust"],  # Remote Data Storage
    "M1030": ["network segmentation", "vlan", "micro-segmentation"],  # Network Segmentation
    "M1031": ["ids/ips", "network intrusion prevention"],  # Network Intrusion Prevention
    "M1032": ["mfa", "2fa"],  # Multi-factor Authentication
    "M1033": ["rate limiting", "api gateway"],  # Limit Software Installation
    "M1034": ["least privilege", "iam"],  # Limit Hardware Installation
    "M1035": ["api gateway", "rate limiting"],  # Limit Access to Resource Over Network
    "M1036": ["least privilege", "iam"],  # Account Use Policies
    "M1037": ["firewall", "waf", "rate limiting", "ids/ips"],  # Filter Network Traffic
    "M1038": ["code signing", "application whitelisting"],  # Execution Prevention
    "M1039": ["least privilege", "sandbox"],  # Environment Variable Permissions
    "M1040": ["behavioral analysis", "edr"],  # Behavior Prevention on Endpoint
    "M1041": ["encryption at rest", "encryption in transit", "tls", "database encryption"],  # Encrypt Sensitive Information
    "M1042": ["application whitelisting", "least privilege"],  # Disable or Remove Feature or Program
    "M1043": ["least privilege", "iam"],  # Credential Access Protection
    "M1044": ["least privilege", "iam"],  # Restrict Library Loading
    "M1045": ["code signing", "integrity monitoring"],  # Code Signing
    "M1046": ["antivirus", "edr"],  # Boot Integrity
    "M1047": ["logging", "audit log", "siem"],  # Audit
    "M1048": ["sandbox", "container isolation", "vm isolation"],  # Application Isolation and Sandboxing
    "M1049": ["edr", "antivirus"],  # Antivirus/Antimalware
    "M1050": ["waf", "input validation", "parameterized queries"],  # Exploit Protection
    "M1051": ["patching", "vulnerability management"],  # Update Software
    "M1052": ["user training", "phishing simulation"],  # User Account Control
    "M1053": ["backup", "database replication", "disaster recovery"],  # Data Backup
    "M1054": ["patching", "auto-update"],  # Software Configuration
    "M1055": ["application control", "waf"],  # Do Not Mitigate
}


# ============================================================================
# THREAT-DRIVEN RECOMMENDATION ENGINE
# ============================================================================

def generate_threat_driven_controls(
    ground_truth: Dict,
    present_controls: Set[str],
    nodes: Dict[str, Dict],
    architecture_type: str,
    max_recommendations: int = 6
) -> List[Dict]:
    """
    Generate control recommendations driven by MITRE techniques in attack paths.

    Args:
        ground_truth: Ground truth with attack paths (must have 'techniques' field)
        present_controls: Set of controls already present
        nodes: Architecture nodes for confidence calculation
        architecture_type: Type of architecture for context-aware confidence
        max_recommendations: Maximum controls to recommend

    Returns:
        List of dicts with:
        {
            "control": "control name",
            "priority": "critical|high|medium",
            "mitigations": ["M1032", "M1047"],
            "techniques": ["T1078", "T1110"],
            "attack_paths": [0, 2],  # Which paths it addresses
            "rationale": "Mitigates T1078 (Valid Accounts) in 2 attack paths",
            "confidence": {
                "score": 0.85,
                "level": "HIGH",
                "breakdown": {...}
            }
        }
    """
    mitre = MitreHelper(use_local=True)
    attack_paths = ground_truth.get("expected_attack_paths", [])
    rapids = ground_truth.get("rapids_assessment", {})

    if not attack_paths:
        logger.warning("No attack paths found - cannot generate threat-driven controls")
        return []

    # Step 1: Collect all techniques from attack paths
    technique_to_paths = defaultdict(list)  # technique_id -> [path_indices]
    all_techniques = []

    for path_idx, path in enumerate(attack_paths):
        techniques = path.get("techniques", [])
        for tech_id in techniques:
            technique_to_paths[tech_id].append(path_idx)
            all_techniques.append(tech_id)

    if not all_techniques:
        logger.warning("No techniques mapped to attack paths")
        return []

    logger.info(f"Found {len(set(all_techniques))} unique MITRE techniques across {len(attack_paths)} attack paths")

    # Step 2: Get MITRE mitigations for these techniques
    mitigations_data = mitre.get_mitigations_for_techniques(list(set(all_techniques)))

    logger.info(f"MITRE recommends {len(mitigations_data)} mitigations for these techniques")

    # Step 3: Map mitigations to implementable controls
    control_recommendations = defaultdict(lambda: {
        "mitigations": set(),
        "techniques": set(),
        "attack_paths": set(),
        "score": 0,
        "priority": "medium"
    })

    for mitigation in mitigations_data:
        mit_id = mitigation["mitigation_id"]
        mit_name = mitigation["mitigation_name"]
        addresses_techniques = mitigation.get("addresses_techniques", [])

        # Map to implementable controls
        controls = MITIGATION_TO_CONTROLS.get(mit_id, [])
        if not controls:
            # Fallback: try to extract control from mitigation name
            controls = [mit_name.lower()]

        for control in controls:
            # Skip if already present
            if control in present_controls:
                continue

            # Calculate score based on how many attack paths this addresses
            paths_addressed = set()
            for tech in addresses_techniques:
                paths_addressed.update(technique_to_paths.get(tech, []))

            if not paths_addressed:
                continue  # This mitigation doesn't address any of our attack paths

            # Weight by attack path criticality
            criticality_weight = sum(
                attack_paths[idx].get("criticality", 0.5)
                for idx in paths_addressed
            )

            control_recommendations[control]["mitigations"].add(mit_id)
            control_recommendations[control]["techniques"].update(addresses_techniques)
            control_recommendations[control]["attack_paths"].update(paths_addressed)
            control_recommendations[control]["score"] += criticality_weight

    # Step 4: Add RAPIDS-based priority boosting
    for control, data in control_recommendations.items():
        # Check if control addresses high-risk RAPIDS threats
        rapids_boost = 0

        for threat_type, scores in rapids.items():
            risk = scores.get("risk", 0)
            if risk < 60:
                continue  # Only boost for high-risk threats

            # Ransomware
            if threat_type == "ransomware" and control in ["backup", "edr", "network segmentation"]:
                rapids_boost += (risk / 100) * 2

            # Application vulns
            elif threat_type == "application_vulns" and control in ["waf", "input validation", "rate limiting", "prompt filtering"]:
                rapids_boost += (risk / 100) * 2

            # Phishing
            elif threat_type == "phishing" and control in ["mfa", "email gateway", "user training"]:
                rapids_boost += (risk / 100) * 1.5

            # Insider threat
            elif threat_type == "insider_threat" and control in ["logging", "audit log", "least privilege", "dlp"]:
                rapids_boost += (risk / 100) * 1.5

            # DoS
            elif threat_type == "dos" and control in ["ddos protection", "rate limiting", "cdn"]:
                rapids_boost += (risk / 100) * 1.5

        data["score"] += rapids_boost

    # Step 5: Prioritize and format results
    results = []
    for control, data in control_recommendations.items():
        num_paths = len(data["attack_paths"])
        num_techniques = len(data["techniques"])
        score = data["score"]

        # Determine priority based on score and coverage
        if score >= 2.0 or num_paths >= 3:
            priority = "critical"
        elif score >= 1.0 or num_paths >= 2:
            priority = "high"
        else:
            priority = "medium"

        # Build rationale
        sample_techniques = list(data["techniques"])[:3]
        technique_names = []
        for tech_id in sample_techniques:
            tech = mitre.find_technique(tech_id)
            if tech:
                technique_names.append(f"{tech_id} ({tech.get('name', 'Unknown')})")
            else:
                technique_names.append(tech_id)

        rationale = f"Mitigates {num_techniques} MITRE technique(s) across {num_paths} attack path(s): {', '.join(technique_names)}"

        results.append({
            "control": control,
            "priority": priority,
            "mitigations": sorted(list(data["mitigations"])),
            "techniques": sorted(list(data["techniques"])),
            "attack_paths": sorted(list(data["attack_paths"])),
            "score": round(score, 2),
            "rationale": rationale
        })

    # Sort by score (descending)
    results.sort(key=lambda x: (-x["score"], -len(x["attack_paths"])))

    # Add confidence scores
    results_with_confidence = add_confidence_to_recommendations(
        results,
        attack_paths,
        nodes,
        rapids,
        architecture_type
    )

    # Log for transparency
    logger.info(f"Generated {len(results_with_confidence)} threat-driven control recommendations:")
    for i, rec in enumerate(results_with_confidence[:max_recommendations], 1):
        conf = rec.get("confidence", {})
        logger.info(f"  {i}. {rec['control']} ({rec['priority']}, score={rec['score']:.2f}, confidence={conf.get('level', 'N/A')} {conf.get('score', 0):.0%})")
        logger.info(f"     → Addresses {len(rec['attack_paths'])} paths via {len(rec['mitigations'])} MITRE mitigations")
        logger.info(f"     → {rec.get('enhanced_rationale', rec['rationale'])}")

    return results_with_confidence[:max_recommendations]


def extract_control_names(recommendations: List[Dict]) -> List[str]:
    """Extract just the control names from recommendations."""
    return [rec["control"] for rec in recommendations]


def format_control_with_rationale(recommendations: List[Dict]) -> str:
    """Format controls with their MITRE-backed rationale for reporting."""
    lines = []
    for i, rec in enumerate(recommendations, 1):
        lines.append(f"{i}. {rec['control'].upper()} ({rec['priority']})")
        lines.append(f"   MITRE Mitigations: {', '.join(rec['mitigations'])}")
        lines.append(f"   {rec['rationale']}")
        lines.append("")
    return "\n".join(lines)
