"""
Confidence Scoring for Threat-Driven Control Recommendations

Calculates confidence scores based on:
1. Technique Mapping Confidence (how certain are we about MITRE techniques?)
2. Mitigation-to-Control Mapping (how direct is the MITRE mitigation → control?)
3. Attack Path Coverage (how many paths does this control address?)
4. RAPIDS Validation (does high RAPIDS risk support this recommendation?)
5. Architecture Context (is this control relevant to this architecture type?)

Confidence Levels:
- HIGH (80-100%): Strong evidence from multiple sources
- MEDIUM (60-79%): Good evidence but some uncertainty
- LOW (40-59%): Weak evidence or indirect mapping
"""

from typing import Dict, List, Tuple
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# MITIGATION-TO-CONTROL MAPPING CONFIDENCE
# ============================================================================

# Direct mappings have HIGH confidence (the control IS the mitigation)
# Indirect mappings have MEDIUM/LOW confidence (control implements part of mitigation)
MITIGATION_CONTROL_CONFIDENCE = {
    # HIGH confidence - direct 1:1 mapping
    "M1032": {"mfa": 1.0, "2fa": 1.0},  # Multi-factor Authentication
    "M1053": {"backup": 1.0, "database replication": 0.9},  # Data Backup
    "M1041": {"encryption at rest": 1.0, "encryption in transit": 1.0, "tls": 1.0},  # Encrypt Sensitive Information
    "M1030": {"network segmentation": 1.0, "vlan": 0.9, "micro-segmentation": 1.0},  # Network Segmentation
    "M1031": {"ids/ips": 1.0, "network intrusion prevention": 1.0},  # Network Intrusion Prevention
    "M1048": {"sandbox": 1.0, "container isolation": 0.9, "vm isolation": 0.9},  # Application Isolation
    "M1049": {"edr": 1.0, "antivirus": 0.9},  # Antivirus/Antimalware
    "M1050": {"waf": 1.0, "input validation": 0.9, "parameterized queries": 0.9},  # Exploit Protection

    # MEDIUM confidence - control implements part of mitigation
    "M1026": {"least privilege": 0.8, "iam": 0.7, "rbac": 0.8},  # Privileged Account Management
    "M1037": {"firewall": 0.8, "waf": 0.8, "rate limiting": 0.7, "ids/ips": 0.7},  # Filter Network Traffic
    "M1047": {"logging": 0.8, "audit log": 0.8, "siem": 0.9},  # Audit
    "M1051": {"patching": 0.8, "vulnerability management": 0.8},  # Update Software

    # LOW confidence - indirect or partial implementation
    "M1018": {"user account management": 0.6, "least privilege": 0.5},  # User Account Management
    "M1027": {"patching": 0.5, "vulnerability scanning": 0.5},  # Password Policies (indirect)
    "M1017": {"patching": 0.4, "vulnerability scanning": 0.4},  # User Training (indirect)
}


def get_mitigation_control_confidence(mitigation_id: str, control: str) -> float:
    """
    Get confidence score for mapping a MITRE mitigation to a control.

    Returns: 0.0-1.0 (1.0 = highest confidence)
    """
    if mitigation_id not in MITIGATION_CONTROL_CONFIDENCE:
        # Unknown mitigation - default to medium-low confidence
        return 0.5

    control_scores = MITIGATION_CONTROL_CONFIDENCE[mitigation_id]
    return control_scores.get(control, 0.5)  # Default to medium if not specified


# ============================================================================
# TECHNIQUE MAPPING CONFIDENCE
# ============================================================================

def calculate_technique_mapping_confidence(
    path: Dict,
    nodes: Dict[str, Dict]
) -> float:
    """
    Calculate confidence in MITRE technique mapping for an attack path.

    Factors:
    - Entry point clarity (internet/public = high, generic = low)
    - Target sensitivity (database/secrets = high, cache = medium)
    - Path length (shorter = more confident)
    - Component specificity (specific tech vs generic labels)

    Returns: 0.0-1.0
    """
    techniques = path.get("techniques", [])
    if not techniques:
        return 0.3  # Low confidence if no techniques mapped

    path_nodes = path.get("path", [])
    entry_label = nodes[path_nodes[0]].get("label", "").lower() if path_nodes else ""
    target_label = nodes[path_nodes[-1]].get("label", "").lower() if len(path_nodes) > 1 else ""

    # Entry point confidence
    entry_confidence = 0.5
    if any(kw in entry_label for kw in ["internet", "public", "external"]):
        entry_confidence = 0.9  # High - clear external entry
    elif any(kw in entry_label for kw in ["user", "mobile", "client"]):
        entry_confidence = 0.8  # Good - user entry point
    elif entry_label:
        entry_confidence = 0.6  # Medium - has label but unclear

    # Target confidence
    target_confidence = 0.5
    if any(kw in target_label for kw in ["database", "db", "secret", "credential", "key"]):
        target_confidence = 0.9  # High - clear sensitive target
    elif any(kw in target_label for kw in ["admin", "api", "storage", "file"]):
        target_confidence = 0.7  # Good - valuable target
    elif target_label:
        target_confidence = 0.6  # Medium - has label

    # Path length confidence (shorter = more confident)
    hop_count = path.get("hop_count", 10)
    if hop_count <= 2:
        path_confidence = 0.9
    elif hop_count <= 4:
        path_confidence = 0.7
    else:
        path_confidence = 0.5

    # Weighted average
    overall = (entry_confidence * 0.4 + target_confidence * 0.4 + path_confidence * 0.2)
    return round(overall, 2)


# ============================================================================
# OVERALL RECOMMENDATION CONFIDENCE
# ============================================================================

def calculate_recommendation_confidence(
    control: str,
    recommendation_data: Dict,
    attack_paths: List[Dict],
    nodes: Dict[str, Dict],
    rapids_assessment: Dict,
    architecture_type: str
) -> Tuple[float, str, Dict]:
    """
    Calculate overall confidence score for a control recommendation.

    Returns: (confidence_score, confidence_level, confidence_breakdown)
    """
    # Factor 1: Technique mapping confidence (average across paths)
    path_indices = recommendation_data["attack_paths"]
    technique_confidences = []
    for idx in path_indices:
        if idx < len(attack_paths):
            path_conf = calculate_technique_mapping_confidence(attack_paths[idx], nodes)
            technique_confidences.append(path_conf)

    avg_technique_conf = sum(technique_confidences) / len(technique_confidences) if technique_confidences else 0.5

    # Factor 2: Mitigation-to-control mapping confidence (average)
    mitigation_ids = recommendation_data["mitigations"]
    mapping_confidences = []
    for mit_id in mitigation_ids:
        conf = get_mitigation_control_confidence(mit_id, control)
        mapping_confidences.append(conf)

    avg_mapping_conf = sum(mapping_confidences) / len(mapping_confidences) if mapping_confidences else 0.5

    # Factor 3: Attack path coverage (more paths = higher confidence)
    num_paths = len(path_indices)
    total_paths = len(attack_paths)
    coverage_conf = min(1.0, num_paths / max(1, total_paths * 0.5))  # 50% coverage = max

    # Factor 4: RAPIDS validation (does high RAPIDS risk support this?)
    rapids_conf = 0.5  # Neutral by default
    control_lower = control.lower()

    for threat_type, scores in rapids_assessment.items():
        risk = scores.get("risk", 0)
        if risk < 60:
            continue  # Only consider high-risk threats

        # Check if control addresses this RAPIDS threat
        if threat_type == "ransomware" and control_lower in ["backup", "edr", "network segmentation"]:
            rapids_conf = max(rapids_conf, 0.9)
        elif threat_type == "application_vulns" and control_lower in ["waf", "input validation", "rate limiting"]:
            rapids_conf = max(rapids_conf, 0.9)
        elif threat_type == "phishing" and control_lower in ["mfa", "email gateway", "user training"]:
            rapids_conf = max(rapids_conf, 0.9)
        elif threat_type == "insider_threat" and control_lower in ["logging", "least privilege", "dlp"]:
            rapids_conf = max(rapids_conf, 0.8)
        elif threat_type == "dos" and control_lower in ["ddos protection", "rate limiting", "cdn"]:
            rapids_conf = max(rapids_conf, 0.9)

    # Factor 5: Architecture context relevance
    context_conf = 0.7  # Default
    if architecture_type == "ai_system" and control_lower in ["prompt filtering", "rate limiting", "sandbox"]:
        context_conf = 1.0  # Critical for AI systems
    elif architecture_type == "web_app" and control_lower in ["waf", "rate limiting", "input validation"]:
        context_conf = 0.9  # Highly relevant for web apps
    elif architecture_type == "iot" and control_lower in ["network segmentation", "ids/ips"]:
        context_conf = 0.9  # Critical for IoT

    # Weighted composite confidence
    confidence_score = (
        avg_technique_conf * 0.30 +  # Technique mapping quality
        avg_mapping_conf * 0.30 +    # Mitigation-to-control mapping
        coverage_conf * 0.20 +        # Attack path coverage
        rapids_conf * 0.10 +          # RAPIDS validation
        context_conf * 0.10           # Architecture relevance
    )

    # Determine confidence level
    if confidence_score >= 0.80:
        confidence_level = "HIGH"
    elif confidence_score >= 0.60:
        confidence_level = "MEDIUM"
    else:
        confidence_level = "LOW"

    # Breakdown for transparency
    breakdown = {
        "overall": round(confidence_score, 2),
        "technique_mapping": round(avg_technique_conf, 2),
        "mitigation_control_mapping": round(avg_mapping_conf, 2),
        "attack_path_coverage": round(coverage_conf, 2),
        "rapids_validation": round(rapids_conf, 2),
        "architecture_relevance": round(context_conf, 2),
        "factors": {
            "paths_addressed": f"{num_paths}/{total_paths}",
            "mitigations_count": len(mitigation_ids),
            "techniques_count": len(recommendation_data["techniques"])
        }
    }

    return (confidence_score, confidence_level, breakdown)


def add_confidence_to_recommendations(
    recommendations: List[Dict],
    attack_paths: List[Dict],
    nodes: Dict[str, Dict],
    rapids_assessment: Dict,
    architecture_type: str
) -> List[Dict]:
    """
    Add confidence scores and detailed rationale to recommendations.
    """
    enhanced = []

    for rec in recommendations:
        control = rec["control"]

        # Calculate confidence
        conf_score, conf_level, breakdown = calculate_recommendation_confidence(
            control,
            rec,
            attack_paths,
            nodes,
            rapids_assessment,
            architecture_type
        )

        # Enhanced rationale with threat context
        techniques_list = rec["techniques"][:3]  # Top 3
        threat_context = []

        for tech_id in techniques_list:
            # Find which attack paths contain this technique
            paths_with_tech = [
                idx for idx in rec["attack_paths"]
                if idx < len(attack_paths) and tech_id in attack_paths[idx].get("techniques", [])
            ]
            if paths_with_tech:
                path_nums = ", ".join([f"#{idx+1}" for idx in paths_with_tech[:3]])
                threat_context.append(f"{tech_id} in path(s) {path_nums}")

        enhanced_rationale = f"Mitigates {', '.join(threat_context[:2])}"  # Top 2 threats

        # Add to recommendation
        rec["confidence"] = {
            "score": conf_score,
            "level": conf_level,
            "breakdown": breakdown
        }
        rec["enhanced_rationale"] = enhanced_rationale

        enhanced.append(rec)

    return enhanced
