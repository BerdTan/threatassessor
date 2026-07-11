"""
Exhaustive MITRE Mitigation Mapper

Phase 3B Enhancement: Query ALL MITRE mitigations + RAPIDS-specific controls.

Instead of hard-coded control mappings, this module:
1. Queries MITRE ATT&CK for ALL official mitigations per technique
2. Adds RAPIDS-specific controls (DoS protection, input validation, etc.)
3. Aggregates by frequency (how many techniques/threats does each address?)
4. Ranks by (RAPIDS threat score × coverage)
5. Maps mitigations → implementable controls
6. Validates ≥80% technique coverage

This ensures comprehensive defense across all RAPIDS threat categories.
"""

from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict
import logging

from chatbot.modules.mitre import MitreHelper, get_mitre_helper

logger = logging.getLogger(__name__)


# ============================================================================
# DIR CATEGORY INFERENCE
# ============================================================================

def _infer_dir_category(control_name: str) -> str:
    """
    Infer primary DIR category from control name. Delegates to the canonical
    multi-layer implementation in rapids_driven_controls for consistency.
    """
    from chatbot.modules.rapids_driven_controls import infer_dir_category
    return infer_dir_category(control_name)


# ============================================================================
# MITRE MITIGATION → IMPLEMENTABLE CONTROL MAPPING (COMPREHENSIVE)
# ============================================================================

# Complete mapping: All 42 MITRE Enterprise mitigations → Implementable controls
# Phase 3B: Ensures exhaustive coverage across RAPIDS threat categories
MITIGATION_TO_CONTROL = {
    # === ACCESS CONTROL & IDENTITY (M1026-M1036) ===
    "M1026": "least privilege",  # Privileged Account Management
    "M1027": "password policy",  # Password Policies
    "M1028": "operating system configuration",  # Operating System Configuration
    "M1030": "network segmentation",  # Network Segmentation
    "M1032": "mfa",  # Multi-factor Authentication
    "M1035": "rate limiting",  # Limit Access to Resource Over Network
    "M1036": "account use policies",  # Account Use Policies

    # === PERIMETER & NETWORK (M1031, M1037, M1050) ===
    "M1031": "ids/ips",  # Network Intrusion Prevention
    "M1037": "firewall",  # Filter Network Traffic
    "M1050": "waf",  # Exploit Protection (WAF for web apps)

    # === APPLICATION SECURITY (M1013, M1048, M1051, M1054) ===
    "M1013": "secure development training",  # Application Developer Guidance
    "M1048": "sandboxing",  # Application Isolation and Sandboxing
    "M1051": "patching",  # Update Software
    "M1054": "secure configuration",  # Software Configuration

    # === DETECTION & MONITORING (M1040, M1047, M1049, M1057, M1019) ===
    "M1040": "edr",  # Behavior Prevention on Endpoint
    "M1047": "logging",  # Audit
    "M1049": "antivirus",  # Antivirus/Antimalware
    "M1057": "dlp",  # Data Loss Prevention
    "M1019": "threat intelligence",  # Threat Intelligence Program

    # === RESILIENCE & RECOVERY (M1053, M1029) ===
    "M1053": "backup",  # Data Backup (CRITICAL for ransomware)
    "M1029": "cloud backup",  # Remote Data Storage (offsite backup)

    # === USER & TRAINING (M1017, M1018, M1056) ===
    "M1017": "security awareness training",  # User Training
    "M1018": "user account management",  # User Account Management
    "M1056": "pre-compromise security",  # Pre-compromise (includes training, threat intel)

    # === ENDPOINT HARDENING (M1042, M1045, M1046, M1052) ===
    "M1042": "disable unnecessary features",  # Disable or Remove Feature or Program
    "M1045": "code signing",  # Code Signing
    "M1046": "secure boot",  # Boot Integrity
    "M1052": "user account control",  # User Account Control (Windows UAC)

    # === EXECUTION PREVENTION (M1033, M1038) ===
    "M1033": "application whitelisting",  # Limit Software Installation
    "M1038": "application control",  # Execution Prevention (AppLocker, etc.)

    # === CREDENTIAL PROTECTION (M1041, M1043) ===
    "M1041": "encryption",  # Encrypt Sensitive Information (at rest, in transit)
    "M1043": "credential guard",  # Credential Access Protection (Windows Credential Guard)

    # === FILE & REGISTRY PROTECTION (M1022, M1024, M1044, M1039) ===
    "M1022": "file system permissions",  # Restrict File and Directory Permissions
    "M1024": "registry permissions",  # Restrict Registry Permissions
    "M1044": "restrict library loading",  # Restrict Library Loading (DLL hijacking prevention)
    "M1039": "environment hardening",  # Environment Variable Permissions

    # === CLOUD & CONTAINER (M1060, M1025, M1034) ===
    "M1060": "container security",  # Out-of-Band Communications Channel (repurposed for containers)
    "M1025": "process integrity",  # Privileged Process Integrity
    "M1034": "hardware restrictions",  # Limit Hardware Installation

    # === NETWORK MONITORING (M1020, M1021) ===
    "M1020": "tls inspection",  # SSL/TLS Inspection
    "M1021": "web content filtering",  # Restrict Web-Based Content

    # === PATCHING & VULNERABILITY MGMT (M1015, M1016) ===
    "M1015": "active directory hardening",  # Active Directory Configuration
    "M1016": "vulnerability scanning",  # Vulnerability Scanning

    # === SPECIAL CASES ===
    "M1055": None,  # Do Not Mitigate (explicitly no control - accept risk)
}


# Techniques that MITRE ATT&CK intentionally leaves without preventive mitigations
# (discovery/reconnaissance techniques — ATT&CK's stance: detect, don't prevent).
# We inject detection-oriented controls manually so they don't stay uncovered.
DETECTION_ONLY_TECHNIQUES = {
    "T1083": {
        "control": "file integrity monitoring",
        "mitre_id": "MANUAL-T1083",
        "description": "File and Directory Discovery — monitor for enumeration of sensitive paths",
        "dir_category": "detect",
        "techniques": ["T1083"],
    },
    "T1018": {
        "control": "network monitoring",
        "mitre_id": "MANUAL-T1018",
        "description": "Remote System Discovery — detect internal reconnaissance via network scan alerts",
        "dir_category": "detect",
        "techniques": ["T1018"],
    },
    "T1046": {
        "control": "network monitoring",
        "mitre_id": "MANUAL-T1046",
        "description": "Network Service Discovery — detect port scanning and service enumeration",
        "dir_category": "detect",
        "techniques": ["T1046"],
    },
    "T1057": {
        "control": "edr",
        "mitre_id": "MANUAL-T1057",
        "description": "Process Discovery — EDR detects anomalous process enumeration",
        "dir_category": "detect",
        "techniques": ["T1057"],
    },
}


# MITRE ATLAS technique → implementable control mapping.
# ATT&CK MitreHelper has no data for AML.T* IDs, so we inject controls manually.
# These are the canonical defences for each ATLAS technique across agentic AI architectures.
ATLAS_TECHNIQUE_CONTROLS = {
    "AML.T0051":     {"control": "prompt injection filter",       "dir_category": "prevention",
                      "description": "LLM Prompt Injection — validate/sanitise all inputs before LLM invocation"},
    "AML.T0051.000": {"control": "prompt injection filter",       "dir_category": "prevention",
                      "description": "Direct Prompt Injection — enforce system prompt integrity; reject override attempts"},
    "AML.T0051.001": {"control": "rag content validation",        "dir_category": "prevention",
                      "description": "Indirect Prompt Injection — validate retrieved/ingested content before LLM context injection"},
    "AML.T0054":     {"control": "llm output filtering",          "dir_category": "prevention",
                      "description": "LLM Jailbreak — output guardrails and content policy enforcement"},
    "AML.T0048":     {"control": "rate limiting",                 "dir_category": "isolate",
                      "description": "External Harms — rate-limit LLM/API calls; monitor for resource abuse"},
    "AML.T0020":     {"control": "training data integrity checks", "dir_category": "prevention",
                      "description": "Poison Training Data — validate training/fine-tuning datasets; hash verification"},
    "AML.T0018":     {"control": "model integrity monitoring",    "dir_category": "detect",
                      "description": "Manipulate AI Model — monitor model weights/outputs for drift; signed model artefacts"},
    "AML.T0025":     {"control": "dlp",                           "dir_category": "prevention",
                      "description": "Exfiltration via Cyber Means — DLP on model outputs and API responses"},
    "AML.T0024":     {"control": "api access control",            "dir_category": "prevention",
                      "description": "Exfiltration via AI Inference API — restrict inference API access; log all queries"},
    "AML.T0044":     {"control": "least privilege",               "dir_category": "prevention",
                      "description": "Full AI Model Access — restrict model artefact access to authorised roles only"},
    "AML.T0040":     {"control": "api access control",            "dir_category": "isolate",
                      "description": "AI Model Inference API Access — enforce API key scoping; rate-limit inference endpoints"},
}


def get_all_mitigations_for_techniques(
    technique_ids: List[str],
    mitre: MitreHelper
) -> Dict[str, Dict]:
    """
    Query MITRE for ALL mitigations addressing the given techniques.

    Args:
        technique_ids: List of MITRE technique IDs (e.g., ['T1190', 'T1059'])
        mitre: MitreHelper instance

    Returns:
        Dict mapping mitigation_id → {
            "name": str,
            "techniques": [technique_ids],
            "frequency": int,
            "control_name": str
        }

    Example:
        {
            "M1026": {
                "name": "Privileged Account Management",
                "techniques": ["T1190", "T1078"],
                "frequency": 2,
                "control_name": "least privilege"
            },
            ...
        }
    """
    mitigation_map = defaultdict(lambda: {
        "name": "",
        "techniques": [],
        "frequency": 0,
        "control_name": None
    })

    logger.info(f"Querying MITRE for mitigations of {len(technique_ids)} techniques...")

    for tech_id in technique_ids:
        mitigations = mitre.get_technique_mitigations(tech_id)

        if not mitigations:
            logger.warning(f"No MITRE mitigations found for {tech_id}")
            continue

        logger.debug(f"{tech_id}: Found {len(mitigations)} mitigations")

        for mit in mitigations:
            mit_id = mit["mitigation_id"]
            mit_name = mit["mitigation_name"]

            # Initialize if first time seeing this mitigation
            if not mitigation_map[mit_id]["name"]:
                mitigation_map[mit_id]["name"] = mit_name
                mitigation_map[mit_id]["control_name"] = MITIGATION_TO_CONTROL.get(
                    mit_id,
                    mit_name.lower()  # Fallback: use mitigation name as control
                )

            # Add technique to this mitigation's coverage
            if tech_id not in mitigation_map[mit_id]["techniques"]:
                mitigation_map[mit_id]["techniques"].append(tech_id)
                mitigation_map[mit_id]["frequency"] += 1

    logger.info(f"Found {len(mitigation_map)} unique mitigations across all techniques")

    return dict(mitigation_map)


def rank_mitigations_by_priority(
    mitigation_map: Dict[str, Dict],
    rapids_scores: Dict[str, float]
) -> List[Tuple[str, Dict, float]]:
    """
    Rank mitigations by priority = (frequency × RAPIDS_weight).

    Args:
        mitigation_map: Output from get_all_mitigations_for_techniques()
        rapids_scores: Dict of threat_category → risk_score (0-100)

    Returns:
        List of (mitigation_id, mitigation_data, priority_score) sorted descending

    Priority Calculation:
        priority = technique_count × avg_rapids_risk

    Rationale:
        - Mitigations addressing many techniques = higher leverage
        - RAPIDS risk amplifies priority (focus on high-risk threat categories)
    """
    ranked = []

    # Calculate average RAPIDS risk (simple: mean of all categories)
    avg_rapids_risk = sum(rapids_scores.values()) / len(rapids_scores) if rapids_scores else 50

    for mit_id, mit_data in mitigation_map.items():
        frequency = mit_data["frequency"]

        # Priority = frequency (how many techniques) × RAPIDS amplifier
        priority_score = frequency * (avg_rapids_risk / 50)  # Normalize around 50

        ranked.append((mit_id, mit_data, priority_score))

        logger.debug(f"{mit_id}: frequency={frequency}, priority={priority_score:.1f}")

    # Sort descending by priority
    ranked.sort(key=lambda x: x[2], reverse=True)

    logger.info(f"Ranked {len(ranked)} mitigations by priority")

    return ranked


def build_technique_coverage_map(
    mitigation_map: Dict[str, Dict]
) -> Dict[str, List[str]]:
    """
    Build reverse mapping: technique_id → [mitigation_ids that address it].

    This creates the explicit coverage map for the hybrid approach.

    Args:
        mitigation_map: Output from get_all_mitigations_for_techniques()

    Returns:
        Dict mapping technique_id → list of valid mitigation_ids

    Example:
        {
            "T1059": ["M1026", "M1042", "M1033", ...],
            "T1190": ["M1016", "M1026", "M1030", ...],
            ...
        }
    """
    technique_coverage = defaultdict(list)

    for mit_id, mit_data in mitigation_map.items():
        for tech_id in mit_data["techniques"]:
            technique_coverage[tech_id].append(mit_id)

    return dict(technique_coverage)


def map_mitigations_to_controls(
    ranked_mitigations: List[Tuple[str, Dict, float]],
    controls_present: Set[str],
    max_recommendations: int = 10
) -> List[Dict]:
    """
    Map ranked MITRE mitigations to implementable controls.

    HYBRID APPROACH (Phase 3C Enhancement):
    - Groups multiple MITRE mitigations into unified controls
    - Builds per-technique coverage map (explicit validation)
    - Maintains defense-in-depth (all mitigations listed)

    Args:
        ranked_mitigations: Output from rank_mitigations_by_priority()
        controls_present: Set of control names already implemented
        max_recommendations: Maximum controls to recommend

    Returns:
        List of control dicts:
        [
            {
                "control": "least privilege",
                "mitigations": ["M1016", "M1018", "M1026"],  # All mitigations this control implements
                "techniques": ["T1059", "T1190", ...],  # All techniques addressed
                "technique_coverage": {  # NEW: Explicit per-technique mapping
                    "T1059": ["M1026", "M1042"],  # Only valid mitigations for T1059
                    "T1190": ["M1016", "M1026"],  # M1016 valid for T1190
                    ...
                },
                "frequency": 6,
                "priority_score": 8.4,
                "rationale": "Addresses 6 techniques via 3 mitigations"
            },
            ...
        ]
    """
    controls_lower = {c.lower() for c in controls_present}
    recommended = []

    # Group mitigations by control name
    control_groups = defaultdict(lambda: {
        "mitigations": [],
        "techniques": set(),
        "priority_scores": [],
        "mitigation_data": {}  # Store mitigation data for coverage map
    })

    for mit_id, mit_data, priority_score in ranked_mitigations:
        control_name = mit_data["control_name"]

        # Skip if already present
        if control_name and control_name.lower() in controls_lower:
            continue

        # Group by control name
        control_groups[control_name]["mitigations"].append(mit_id)
        control_groups[control_name]["techniques"].update(mit_data["techniques"])
        control_groups[control_name]["priority_scores"].append(priority_score)
        control_groups[control_name]["mitigation_data"][mit_id] = mit_data

    # Build recommendations from grouped controls
    for control_name, group_data in control_groups.items():
        mitigations = group_data["mitigations"]
        techniques = sorted(list(group_data["techniques"]))
        avg_priority = sum(group_data["priority_scores"]) / len(group_data["priority_scores"])

        # Build per-technique coverage map (HYBRID APPROACH)
        technique_coverage = {}
        for tech_id in techniques:
            # Find which mitigations from this control are valid for this technique
            valid_mitigations = []
            for mit_id, mit_data in group_data["mitigation_data"].items():
                if tech_id in mit_data["techniques"]:
                    valid_mitigations.append(mit_id)

            technique_coverage[tech_id] = valid_mitigations

        # Build rationale
        frequency = len(techniques)
        technique_list = ", ".join(techniques[:5])  # First 5 for brevity
        if len(techniques) > 5:
            technique_list += f", ... ({len(techniques) - 5} more)"

        rationale = f"Addresses {frequency} technique(s) via {len(mitigations)} mitigation(s): {technique_list}"

        recommended.append({
            "control": control_name,
            "name": control_name,  # Keep for backwards compat
            "mitigations": mitigations,  # Defense-in-depth: all mitigations
            "techniques": techniques,  # All techniques addressed
            "technique_coverage": technique_coverage,  # NEW: Explicit per-technique mapping
            "frequency": frequency,
            "priority_score": avg_priority,
            "priority": "high" if avg_priority > 5 else "medium",
            "score": avg_priority,
            "rationale": rationale,
            "confidence": {
                "score": 0.85,  # Higher confidence with explicit coverage map
                "level": "HIGH",
                "factors": [
                    "Exhaustive MITRE mitigation query",
                    "Explicit per-technique validation",
                    "Defense-in-depth grouping"
                ]
            },
            "rapids_threats": [],  # Not RAPIDS-driven, purely technique-based
            "attack_paths": [],  # Will be populated if we match attack path techniques
            "dir_category": _infer_dir_category(control_name)
        })

        logger.info(f"Recommended: {control_name} (priority={avg_priority:.1f}, {len(mitigations)} mitigations, {frequency} techniques)")

        if len(recommended) >= max_recommendations:
            break

    # Sort by priority
    recommended.sort(key=lambda x: x["priority_score"], reverse=True)

    return recommended


def calculate_mitigation_coverage(
    all_technique_mitigations: Dict[str, Dict],
    recommended_controls: List[Dict]
) -> float:
    """
    Calculate what percentage of MITRE mitigations are addressed by recommendations.

    Args:
        all_technique_mitigations: All possible mitigations (from get_all_mitigations_for_techniques)
        recommended_controls: Controls we're recommending

    Returns:
        Coverage percentage (0.0 - 1.0)

    Target: ≥0.80 (80% coverage)
    """
    total_mitigations = len(all_technique_mitigations)

    if total_mitigations == 0:
        return 1.0  # No mitigations needed = 100% coverage

    # Get mitigation IDs from recommendations
    recommended_mit_ids = {
        ctrl["mitre_mitigation_id"]
        for ctrl in recommended_controls
        if "mitre_mitigation_id" in ctrl
    }

    addressed_count = len(recommended_mit_ids)
    coverage = addressed_count / total_mitigations

    logger.info(f"Mitigation coverage: {addressed_count}/{total_mitigations} = {coverage:.1%}")

    return coverage


def validate_mitigation_coverage(
    technique_ids: List[str],
    recommended_controls: List[Dict],
    mitre: MitreHelper,
    threshold: float = 0.80
) -> Dict:
    """
    Validate that recommended controls address ≥80% of techniques.

    Phase 3B Logic:
    - PRIMARY metric: What % of techniques are covered by ≥1 mitigation?
    - SECONDARY metric: What % of total mitigations are addressed?

    We care more about technique coverage than exhaustive mitigation coverage,
    because multiple mitigations may map to the same control (diminishing returns).

    Returns:
        {
            "passed": bool,
            "technique_coverage": float (0-1),
            "mitigation_coverage": float (0-1),
            "threshold": float,
            "total_techniques": int,
            "covered_techniques": int,
            "total_mitigations": int,
            "addressed_mitigations": int,
            "missing_techniques": [technique_ids],
            "missing_mitigations": [mitigation_ids]
        }
    """
    # Get all possible mitigations
    all_mitigations = get_all_mitigations_for_techniques(technique_ids, mitre)

    # Get techniques addressed by recommendations
    covered_techniques = set()
    for ctrl in recommended_controls:
        covered_techniques.update(ctrl.get("techniques_addressed", []))

    # Calculate technique coverage (PRIMARY metric)
    technique_coverage = len(covered_techniques) / len(technique_ids) if technique_ids else 1.0

    # Calculate mitigation coverage (SECONDARY metric)
    mitigation_coverage = calculate_mitigation_coverage(all_mitigations, recommended_controls)

    # Find missing items
    recommended_mit_ids = {
        ctrl["mitre_mitigation_id"]
        for ctrl in recommended_controls
        if "mitre_mitigation_id" in ctrl
    }

    missing_techniques = [t for t in technique_ids if t not in covered_techniques]
    missing_mitigations = [
        mit_id for mit_id in all_mitigations.keys()
        if mit_id not in recommended_mit_ids
    ]

    # PASS if technique coverage ≥ threshold
    passed = technique_coverage >= threshold

    result = {
        "passed": passed,
        "technique_coverage": technique_coverage,  # PRIMARY
        "mitigation_coverage": mitigation_coverage,  # SECONDARY
        "threshold": threshold,
        "total_techniques": len(technique_ids),
        "covered_techniques": len(covered_techniques),
        "total_mitigations": len(all_mitigations),
        "addressed_mitigations": len(recommended_mit_ids),
        "missing_techniques": missing_techniques,
        "missing_mitigations": missing_mitigations
    }

    if passed:
        logger.info(f"✅ Technique coverage validation PASSED: {technique_coverage:.1%} >= {threshold:.1%}")
        logger.info(f"   Secondary - Mitigation coverage: {mitigation_coverage:.1%}")
    else:
        logger.warning(f"⚠️  Technique coverage validation FAILED: {technique_coverage:.1%} < {threshold:.1%}")
        logger.warning(f"   Missing techniques: {missing_techniques}")

    return result


# ============================================================================
# RAPIDS-SPECIFIC CONTROL AUGMENTATION
# ============================================================================

# Controls not in MITRE but critical for RAPIDS threat categories
RAPIDS_SPECIFIC_CONTROLS = {
    "dos": {
        "ddos protection": {
            "rationale": "Mitigates volumetric attacks (L3/L4)",
            "techniques": ["T1498", "T1499"],
            "priority_boost": 2.0  # Critical for DoS category
        },
        "rate limiting": {
            "rationale": "Prevents API abuse and resource exhaustion (L7)",
            "techniques": ["T1498", "T1499"],
            "priority_boost": 1.5
        },
        "load balancer": {
            "rationale": "Distributes traffic, prevents single point of failure",
            "techniques": ["T1498"],
            "priority_boost": 1.2
        },
    },
    "application_vulns": {
        "input validation": {
            "rationale": "Prevents injection attacks at application layer",
            "techniques": ["T1190", "T1059"],
            "priority_boost": 1.8
        },
    },
    "phishing": {
        "email gateway": {
            "rationale": "Filters phishing emails before delivery",
            "techniques": ["T1566"],
            "priority_boost": 1.5
        },
    },
    "supply_chain": {
        "vendor risk management": {
            "rationale": "Assesses third-party security posture",
            "techniques": ["T1199", "T1195"],
            "priority_boost": 1.3
        },
        "sbom": {
            "rationale": "Software Bill of Materials for dependency tracking",
            "techniques": ["T1195"],
            "priority_boost": 1.2
        },
    },
}


def augment_with_rapids_controls(
    mitre_controls: List[Dict],
    rapids_assessment: Dict,
    controls_present: Set[str],
    technique_ids: List[str]
) -> List[Dict]:
    """
    Add RAPIDS-specific controls not covered by MITRE mitigations.

    These are infrastructure/vendor-specific controls that complement MITRE's
    technique-focused mitigations.

    Args:
        mitre_controls: Controls from MITRE mitigation mapping
        rapids_assessment: RAPIDS risk scores
        controls_present: Existing controls
        technique_ids: All techniques from attack paths

    Returns:
        Combined list with RAPIDS controls added
    """
    augmented = list(mitre_controls)
    controls_lower = {c.lower() for c in controls_present}

    # Check each RAPIDS category
    for category, controls in RAPIDS_SPECIFIC_CONTROLS.items():
        rapids_risk = rapids_assessment.get(category, {}).get("risk", 0)

        # Only add if RAPIDS threat is elevated (≥60)
        if rapids_risk < 60:
            continue

        logger.info(f"RAPIDS category '{category}' elevated ({rapids_risk}/100) - adding specific controls")

        for control_name, control_data in controls.items():
            # Skip if already present
            if control_name.lower() in controls_lower:
                continue

            # Check if this control's techniques are in our attack paths
            relevant_techniques = [
                t for t in control_data["techniques"]
                if t in technique_ids
            ]

            if not relevant_techniques:
                logger.debug(f"Skipping {control_name} - no relevant techniques")
                continue

            # Calculate priority based on RAPIDS risk
            base_priority = len(relevant_techniques) * (rapids_risk / 50)
            priority_score = base_priority * control_data["priority_boost"]

            # Add to recommendations
            augmented.append({
                "name": control_name,
                "mitre_mitigation_id": None,  # Not from MITRE
                "mitre_mitigation_name": f"RAPIDS-specific ({category})",
                "techniques_addressed": relevant_techniques,
                "frequency": len(relevant_techniques),
                "priority_score": priority_score,
                "rationale": control_data["rationale"],
                "rapids_category": category
            })

            logger.info(f"Added RAPIDS control: {control_name} (priority={priority_score:.1f}, category={category})")

    # Re-sort by priority
    augmented.sort(key=lambda x: x["priority_score"], reverse=True)

    return augmented


# ============================================================================
# HIGH-LEVEL API
# ============================================================================

def generate_exhaustive_control_recommendations(
    technique_ids: List[str],
    controls_present: Set[str],
    rapids_assessment: Dict,
    mitre: MitreHelper,
    max_recommendations: int = 10
) -> Tuple[List[Dict], Dict]:
    """
    Generate control recommendations using exhaustive MITRE mitigation querying + RAPIDS augmentation.

    Args:
        technique_ids: All MITRE techniques from attack paths
        controls_present: Set of existing control names
        rapids_assessment: RAPIDS risk scores by category
        mitre: MitreHelper instance
        max_recommendations: Maximum controls to recommend

    Returns:
        (recommended_controls, validation_result)

    Process:
        1. Query ALL MITRE mitigations for techniques
        2. Aggregate by frequency (how many techniques each addresses)
        3. Rank by (frequency × RAPIDS risk)
        4. Map to implementable controls
        5. Validate ≥80% mitigation coverage
    """
    logger.info("="*80)
    logger.info("EXHAUSTIVE MITRE MITIGATION ANALYSIS")
    logger.info("="*80)

    # Step 1: Query all mitigations
    all_mitigations = get_all_mitigations_for_techniques(technique_ids, mitre)

    if not all_mitigations:
        logger.warning("No MITRE mitigations found - using fallback recommendations")
        return [], {"passed": False, "coverage": 0.0, "threshold": 0.80}

    # Step 2: Rank by priority
    rapids_scores = {
        category: scores.get("risk", 0)
        for category, scores in rapids_assessment.items()
        if isinstance(scores, dict) and "risk" in scores
    }

    ranked = rank_mitigations_by_priority(all_mitigations, rapids_scores)

    logger.info(f"\nTop 5 mitigations by priority:")
    for mit_id, mit_data, priority in ranked[:5]:
        logger.info(f"  {mit_id} ({mit_data['name']}): priority={priority:.1f}, addresses {mit_data['frequency']} techniques")

    # Step 3: Map to controls
    mitre_controls = map_mitigations_to_controls(
        ranked,
        controls_present,
        max_recommendations
    )

    logger.info(f"\nMITRE-based controls: {len(mitre_controls)}")

    # Step 3b: Augment with RAPIDS-specific controls
    recommended = augment_with_rapids_controls(
        mitre_controls,
        rapids_assessment,
        controls_present,
        technique_ids
    )

    # Trim to max_recommendations after augmentation
    if len(recommended) > max_recommendations:
        logger.info(f"Trimming {len(recommended)} → {max_recommendations} controls (by priority)")
        recommended = recommended[:max_recommendations]

    logger.info(f"\nTotal recommended controls: {len(recommended)} (MITRE + RAPIDS-specific)")

    # Step 4: Validate coverage
    validation = validate_mitigation_coverage(
        technique_ids,
        recommended,
        mitre,
        threshold=0.80
    )

    logger.info("="*80)

    return recommended, validation


def augment_with_exhaustive_mitigations(
    control_recommendations: List[Dict],
    all_techniques: List[str],
    controls_present: List[str],
    rapids_assessment: Dict,
    mitre: 'MitreHelper',
    max_total_recommendations: Optional[int] = None,
    attack_paths: Optional[List[Dict]] = None
) -> List[Dict]:
    """
    Augment existing control recommendations with gap-filling controls from exhaustive MITRE analysis.

    Purpose: Achieve 100% technique coverage by adding controls for uncovered techniques.

    Strategy:
    - No hard limit on control count (max_total_recommendations=None)
    - Add controls iteratively until 100% technique coverage achieved
    - Prioritize by (technique_count × RAPIDS_risk × priority_boost)
    - Stop when all techniques covered (no redundant controls)

    Args:
        control_recommendations: Existing RAPIDS-driven recommendations
        all_techniques: All MITRE techniques from attack paths
        controls_present: Controls already in architecture
        rapids_assessment: RAPIDS threat scores
        mitre: MitreHelper instance
        max_total_recommendations: Optional hard limit (None = no limit, add until 100% coverage)

    Returns:
        Augmented list of control recommendations (sorted by priority)
    """
    # Find uncovered techniques
    covered_techniques = set()
    for ctrl in control_recommendations:
        covered_techniques.update(ctrl.get('techniques', []))

    uncovered_techniques = set(all_techniques) - covered_techniques

    if not uncovered_techniques:
        logger.info("✅ All techniques covered by RAPIDS-driven controls")
        return control_recommendations

    logger.info(f"⚠️  {len(uncovered_techniques)} techniques uncovered: {sorted(uncovered_techniques)}")
    logger.info(f"   Finding gap-filling controls...")

    # Get mitigations for remaining uncovered techniques (after manual injection)
    gap_mitigations = get_all_mitigations_for_techniques(list(uncovered_techniques), mitre)

    # Inject manual detection controls for techniques MITRE intentionally leaves unmapped
    # Also inject ATLAS-specific controls for AML.T* techniques (not in ATT&CK database)
    manual_controls = []
    still_uncovered = set()
    for tid in list(uncovered_techniques):
        if tid in DETECTION_ONLY_TECHNIQUES:
            entry = DETECTION_ONLY_TECHNIQUES[tid]
            ctrl_name = entry["control"]
            already_present = ctrl_name in (controls_present + [c.get('control', '') for c in control_recommendations])
            if not already_present:
                manual_controls.append({
                    "control": ctrl_name,
                    "name": ctrl_name.upper(),
                    "description": entry["description"],
                    "techniques": entry["techniques"],
                    "techniques_addressed": entry["techniques"],
                    "dir_category": entry["dir_category"],
                    "mitre_mitigations": [entry["mitre_id"]],
                    "priority": "medium",
                    "source": "manual_detection",
                })
                logger.info(f"✅ Manual detection control for {tid}: {ctrl_name}")
        elif tid in ATLAS_TECHNIQUE_CONTROLS:
            entry = ATLAS_TECHNIQUE_CONTROLS[tid]
            ctrl_name = entry["control"]
            already_present = ctrl_name in (controls_present + [c.get('control', '') for c in control_recommendations])
            if not already_present:
                manual_controls.append({
                    "control": ctrl_name,
                    "name": ctrl_name.upper(),
                    "description": entry["description"],
                    "techniques": [tid],
                    "techniques_addressed": [tid],
                    "dir_category": entry["dir_category"],
                    "mitre_mitigations": [f"ATLAS-{tid}"],
                    "priority": "high",
                    "source": "atlas_manual",
                })
                logger.info(f"✅ ATLAS control for {tid}: {ctrl_name}")
        else:
            still_uncovered.add(tid)

    if manual_controls:
        control_recommendations = control_recommendations + manual_controls
        uncovered_techniques = still_uncovered

    if not uncovered_techniques:
        return control_recommendations

    if not gap_mitigations:
        logger.warning("No MITRE mitigations found for uncovered techniques")
        return control_recommendations

    # Rank by priority
    rapids_scores = {
        category: scores.get("risk", 0)
        for category, scores in rapids_assessment.items()
        if isinstance(scores, dict) and "risk" in scores
    }

    ranked_gaps = rank_mitigations_by_priority(gap_mitigations, rapids_scores)

    # Map to controls (excluding already present)
    # If max_total_recommendations is None, add all gap controls for 100% coverage
    if max_total_recommendations is None:
        max_gap_controls = len(ranked_gaps)  # No limit
    else:
        max_gap_controls = max(0, max_total_recommendations - len(control_recommendations))

    gap_controls = map_mitigations_to_controls(
        ranked_gaps,
        controls_present + [c['control'] for c in control_recommendations],
        max_recommendations=max_gap_controls
    )

    if gap_controls:
        logger.info(f"✅ Adding {len(gap_controls)} gap-filling controls:")
        for ctrl in gap_controls:
            techniques = ctrl.get('techniques_addressed', ctrl.get('techniques', []))
            techniques_str = ', '.join(techniques[:3])
            if len(techniques) > 3:
                techniques_str += f" +{len(techniques) - 3} more"
            control_name = ctrl.get('name', ctrl.get('control', 'unknown'))
            logger.info(f"   • {control_name} (covers {techniques_str})")

    # Populate attack_paths for gap controls using technique overlap with attack paths
    if attack_paths and gap_controls:
        technique_to_path_indices = {}
        for idx, path in enumerate(attack_paths):
            for tech in path.get('techniques', []):
                technique_to_path_indices.setdefault(tech, []).append(idx)

        for ctrl in gap_controls:
            matched = set()
            for tech in ctrl.get('techniques', []):
                matched.update(technique_to_path_indices.get(tech, []))
            ctrl['attack_paths'] = sorted(matched)
            if matched:
                logger.info(f"Gap control '{ctrl.get('control')}' mapped to paths {sorted(matched)} via technique overlap")

    # Merge and re-sort by priority
    all_controls = control_recommendations + gap_controls
    all_controls.sort(key=lambda c: c.get('priority_score', c.get('score', 0)), reverse=True)

    # Calculate final coverage
    final_covered = set()
    for ctrl in all_controls:
        final_covered.update(ctrl.get('techniques', []))

    coverage = len(final_covered) / len(all_techniques) if all_techniques else 1.0
    logger.info(f"Final technique coverage: {len(final_covered)}/{len(all_techniques)} ({coverage:.1%})")

    # Optional: Trim to max if hard limit specified (not recommended)
    if max_total_recommendations is not None and len(all_controls) > max_total_recommendations:
        logger.warning(f"Hard limit {max_total_recommendations} reached - trimming {len(all_controls) - max_total_recommendations} controls")
        all_controls = all_controls[:max_total_recommendations]

    return all_controls


if __name__ == "__main__":
    # Test case
    import sys
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    print("="*80)
    print("EXHAUSTIVE MITIGATION MAPPER TEST")
    print("="*80)

    # Initialize MITRE
    mitre = get_mitre_helper()

    # Test techniques
    test_techniques = ["T1190", "T1059", "T1078", "T1213"]
    test_controls = {"WAF", "Rate Limiting"}
    test_rapids = {
        "application_vulns": {"risk": 80},
        "phishing": {"risk": 60},
        "ransomware": {"risk": 70}
    }

    print(f"\nTest Techniques: {test_techniques}")
    print(f"Existing Controls: {test_controls}")
    print(f"RAPIDS Scores: {test_rapids}")

    recommended, validation = generate_exhaustive_control_recommendations(
        test_techniques,
        test_controls,
        test_rapids,
        mitre,
        max_recommendations=10
    )

    print("\n" + "="*80)
    print("RECOMMENDED CONTROLS")
    print("="*80)
    for ctrl in recommended[:5]:
        print(f"\n{ctrl['name'].upper()}")
        print(f"  MITRE: {ctrl['mitre_mitigation_id']} ({ctrl['mitre_mitigation_name']})")
        print(f"  Priority: {ctrl['priority_score']:.1f}")
        print(f"  Addresses: {', '.join(ctrl['techniques_addressed'])}")

    print("\n" + "="*80)
    print("VALIDATION RESULT")
    print("="*80)
    print(f"Technique Coverage (PRIMARY): {validation['technique_coverage']:.1%} (threshold: {validation['threshold']:.1%})")
    print(f"Mitigation Coverage (SECONDARY): {validation['mitigation_coverage']:.1%}")
    print(f"Status: {'✅ PASS' if validation['passed'] else '❌ FAIL'}")
    print(f"Techniques Covered: {validation['covered_techniques']}/{validation['total_techniques']}")
    print(f"Mitigations Addressed: {validation['addressed_mitigations']}/{validation['total_mitigations']}")

    if validation['missing_techniques']:
        print(f"\nMissing techniques: {validation['missing_techniques']}")

    if validation['missing_mitigations']:
        print(f"Missing mitigations: {validation['missing_mitigations'][:5]}...")

    print("="*80)
