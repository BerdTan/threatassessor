"""
RAPIDS-Driven Control Recommendation Engine

RAPIDS threats are the PRIMARY driver for control recommendations.
Attack paths and MITRE techniques serve as VALIDATION and EVIDENCE.

Approach:
1. Start with RAPIDS threat categories (Ransomware, Application Vulns, Phishing, etc.)
2. For each HIGH-RISK RAPIDS threat, identify mandatory controls
3. Use attack paths as EVIDENCE that the threat is exploitable in this architecture
4. Map controls to MITRE for traceability
5. Boost confidence when attack paths confirm RAPIDS assessment

This ensures controls address ACTUAL threat scenarios, not just technique patterns.
"""

from typing import Dict, List, Set, Tuple
import logging
from collections import defaultdict

from chatbot.modules.mitre import MitreHelper
from chatbot.modules.confidence_scoring import add_confidence_to_recommendations

logger = logging.getLogger(__name__)


# ============================================================================
# DIR CATEGORY INFERENCE (for controls without hop-level enrichment)
# ============================================================================

def infer_dir_category(control_name: str) -> str:
    """
    Infer DIR category from control name.

    Used when control is recommended by RAPIDS but not enriched by hop analysis.

    Returns: "prevention", "detect", "isolate", or "respond"
    """
    control_lower = control_name.lower()

    # DETECT: Monitoring, logging, alerting, scanning, assessment
    if any(kw in control_lower for kw in ["log", "monitor", "siem", "ids", "detect", "alert", "audit", "behavioral", "anomaly", "scan", "assessment", "intelligence", "dlp"]):
        return "detect"

    # ISOLATE: Access control, segmentation, containment
    if any(kw in control_lower for kw in ["segment", "privilege", "rbac", "isolat", "contain", "acl", "vlan", "quarantine", "timeout", "lockout"]):
        return "isolate"

    # RESPOND: Recovery, remediation, incident response
    if any(kw in control_lower for kw in ["backup", "recover", "restore", "incident", "response", "rollback", "failover", "reimage", "forensic"]):
        return "respond"

    # PREVENTION: Default (blocks, filters, validates)
    return "prevention"


# ============================================================================
# RAPIDS THREAT → MANDATORY CONTROLS MAPPING
# ============================================================================

RAPIDS_MANDATORY_CONTROLS = {
    "ransomware": {
        "critical": [
            ("backup", "Data recovery is MANDATORY for ransomware resilience"),
            ("edr", "Detect ransomware behavior before encryption"),
        ],
        "high": [
            ("network segmentation", "Limit ransomware spread across systems"),
            ("least privilege", "Reduce attack surface for privilege escalation"),
        ],
        "medium": [
            ("patching", "Close vulnerabilities used for initial access"),
            ("user training", "Prevent social engineering vectors"),
        ]
    },

    "application_vulns": {
        "critical": [
            ("waf", "Block OWASP Top 10 attacks at perimeter"),
            ("input validation", "Prevent injection attacks"),
        ],
        "high": [
            ("rate limiting", "Prevent brute force and enumeration"),
            ("patching", "Fix known CVEs in application stack"),
        ],
        "medium": [
            ("api gateway", "Centralized authentication and monitoring"),
            ("vulnerability scanning", "Continuous security assessment"),
        ]
    },

    "phishing": {
        "critical": [
            ("mfa", "Mitigate stolen credential impact"),
        ],
        "high": [
            ("email gateway", "Filter phishing emails before delivery"),
            ("user training", "Build human firewall"),
        ],
        "medium": [
            ("least privilege", "Limit damage from compromised accounts"),
            ("logging", "Detect anomalous authentication patterns"),
        ]
    },

    "insider_threat": {
        "critical": [
            ("logging", "Audit trail for forensics and detection"),
            ("least privilege", "Limit insider damage potential"),
        ],
        "high": [
            ("dlp", "Prevent data exfiltration"),
            ("audit log", "Track privileged actions"),
        ],
        "medium": [
            ("user training", "Awareness of insider threat indicators"),
            ("behavioral analysis", "Detect anomalous user behavior"),
        ]
    },

    "dos": {
        "critical": [
            ("ddos protection", "Absorb volumetric attacks"),
            ("rate limiting", "Prevent resource exhaustion"),
        ],
        "high": [
            ("cdn", "Distribute traffic and absorb attacks"),
            ("load balancer", "Distribute load and failover"),
        ],
        "medium": [
            ("monitoring", "Detect DoS attacks early"),
            ("auto-scaling", "Handle traffic spikes"),
        ]
    },

    "supply_chain": {
        "critical": [
            ("container scanning", "Detect vulnerable dependencies"),
            ("code signing", "Verify code provenance"),
        ],
        "high": [
            ("secrets management", "Prevent credential leakage in code"),
            ("vulnerability scanning", "Continuous dependency monitoring"),
        ],
        "medium": [
            ("sbom", "Track software bill of materials"),
            ("vendor assessment", "Evaluate third-party security"),
        ]
    }
}


# ============================================================================
# RAPIDS-FIRST RECOMMENDATION ENGINE
# ============================================================================

def generate_rapids_driven_controls(
    ground_truth: Dict,
    present_controls: Set[str],
    nodes: Dict[str, Dict],
    architecture_type: str,
    max_recommendations: int = 6
) -> List[Dict]:
    """
    Generate controls driven by RAPIDS threat assessment.

    Attack paths serve as EVIDENCE that RAPIDS threats are exploitable.

    Returns: List of control recommendations with RAPIDS context
    """
    mitre = MitreHelper(use_local=True)

    rapids = ground_truth.get("rapids_assessment", {})
    attack_paths = ground_truth.get("expected_attack_paths", [])

    if not rapids:
        logger.warning("No RAPIDS assessment - cannot generate RAPIDS-driven controls")
        return []

    # Sort RAPIDS threats by risk (highest first)
    rapids_by_risk = sorted(
        rapids.items(),
        key=lambda x: x[1].get("risk", 0),
        reverse=True
    )

    logger.info(f"RAPIDS-DRIVEN RECOMMENDATIONS (Primary Driver)")
    logger.info("=" * 80)
    logger.info("RAPIDS Threat Priorities:")
    for threat_type, scores in rapids_by_risk[:6]:
        risk = scores.get("risk", 0)
        defensibility = scores.get("defensibility", 0)
        indicator = "🔴" if risk >= 70 else "🟠" if risk >= 50 else "🟡"
        logger.info(f"  {indicator} {threat_type.replace('_', ' ').upper()}: Risk={risk}/100, Defensibility={defensibility}/100")

    logger.info("")

    # Collect recommendations from RAPIDS threats
    recommendations = {}

    for threat_type, scores in rapids_by_risk:
        risk = scores.get("risk", 0)
        defensibility = scores.get("defensibility", 0)

        # Only recommend for moderate+ risk
        if risk < 40:
            continue

        # Get mandatory controls for this threat
        threat_controls = RAPIDS_MANDATORY_CONTROLS.get(threat_type, {})

        # Determine priority tier based on risk
        if risk >= 70:
            priority_tiers = ["critical", "high"]
        elif risk >= 50:
            priority_tiers = ["critical", "high", "medium"]
        else:
            priority_tiers = ["high", "medium"]

        for tier in priority_tiers:
            for control, rationale in threat_controls.get(tier, []):
                # Skip if already present
                if control in present_controls:
                    continue

                # Initialize or update recommendation
                if control not in recommendations:
                    recommendations[control] = {
                        "control": control,
                        "rapids_threats": [],
                        "rapids_risk_score": 0,
                        "priority": tier,
                        "rationale": [],
                        "attack_path_evidence": [],
                        "mitigations": set(),
                        "techniques": set()
                    }

                # Add RAPIDS threat context
                recommendations[control]["rapids_threats"].append(threat_type)
                recommendations[control]["rapids_risk_score"] += risk
                recommendations[control]["rationale"].append(
                    f"{threat_type.replace('_', ' ').title()} (risk={risk}/100): {rationale}"
                )

    logger.info("Controls recommended by RAPIDS assessment:")
    for control in recommendations:
        threats = recommendations[control]["rapids_threats"]
        logger.info(f"  • {control} → Addresses {len(threats)} RAPIDS threat(s): {', '.join(threats)}")

    logger.info("")

    # NOW use attack paths as VALIDATION/EVIDENCE
    logger.info("Validating with attack path evidence...")
    logger.info("=" * 80)

    # Map MITRE techniques from attack paths
    technique_to_paths = defaultdict(list)
    for path_idx, path in enumerate(attack_paths):
        for tech_id in path.get("techniques", []):
            technique_to_paths[tech_id].append(path_idx)

    if technique_to_paths:
        # Get MITRE mitigations for techniques
        all_techniques = list(technique_to_paths.keys())
        mitigations_data = mitre.get_mitigations_for_techniques(all_techniques)

        logger.info(f"Found {len(all_techniques)} MITRE techniques in {len(attack_paths)} attack paths")
        logger.info(f"MITRE recommends {len(mitigations_data)} mitigations")

        # Cross-reference: Do our RAPIDS-driven controls also address these techniques?
        for rec_data in recommendations.values():
            control = rec_data["control"]

            # Check which techniques this control can address
            for mitigation in mitigations_data:
                mit_id = mitigation["mitigation_id"]
                addresses_techs = mitigation.get("addresses_techniques", [])

                # Import mitigation-to-control mapping
                from chatbot.modules.threat_driven_controls import MITIGATION_TO_CONTROLS

                # Does this mitigation map to our control?
                if control in MITIGATION_TO_CONTROLS.get(mit_id, []):
                    rec_data["mitigations"].add(mit_id)
                    rec_data["techniques"].update(addresses_techs)

                    # Which attack paths have these techniques?
                    for tech_id in addresses_techs:
                        if tech_id in technique_to_paths:
                            rec_data["attack_path_evidence"].extend(technique_to_paths[tech_id])

        # Log evidence alignment
        for control, data in recommendations.items():
            if data["attack_path_evidence"]:
                unique_paths = len(set(data["attack_path_evidence"]))
                logger.info(f"  ✓ {control}: Confirmed by {unique_paths} attack path(s)")
            else:
                logger.info(f"  ⚠️  {control}: No attack path evidence (pure RAPIDS recommendation)")
    else:
        logger.warning("No attack path techniques available for validation")

    logger.info("")

    # Convert to standard format
    results = []
    for control, data in recommendations.items():
        # Calculate score: RAPIDS risk is primary, attack path evidence boosts
        base_score = data["rapids_risk_score"] / 10.0  # Normalize (100 risk = 10 score)
        evidence_boost = len(set(data["attack_path_evidence"])) * 2.0  # Each path adds +2
        total_score = base_score + evidence_boost

        # Determine priority
        if total_score >= 15 or data["rapids_risk_score"] >= 140:
            priority = "critical"
        elif total_score >= 8 or data["rapids_risk_score"] >= 100:
            priority = "high"
        else:
            priority = "medium"

        # Build comprehensive rationale
        rapids_context = f"RAPIDS: {', '.join([t.replace('_', ' ').title() for t in data['rapids_threats']])}"
        attack_evidence = ""
        if data["attack_path_evidence"]:
            unique_paths = sorted(set(data["attack_path_evidence"]))
            attack_evidence = f" | Confirmed by attack path(s) #{', #'.join(str(p+1) for p in unique_paths[:5])}"

        rationale = f"{rapids_context}{attack_evidence}"

        # Infer DIR category if not already set
        dir_category = infer_dir_category(control)

        results.append({
            "control": control,
            "priority": priority,
            "score": round(total_score, 2),
            "rapids_threats": data["rapids_threats"],
            "rapids_risk_score": data["rapids_risk_score"],
            "mitigations": sorted(list(data["mitigations"])),
            "techniques": sorted(list(data["techniques"])),
            "attack_paths": sorted(set(data["attack_path_evidence"])),
            "rationale": rationale,
            "detailed_rationale": data["rationale"],
            "dir_category": dir_category  # Inferred from control name
        })

    # Sort by score (RAPIDS-driven + evidence boost)
    results.sort(key=lambda x: (-x["score"], -x["rapids_risk_score"]))

    # Phase 3B-2: Integrate layered defense (hop-level DDIR + resilience + SPOF)
    logger.info("")
    logger.info("Phase 3B-2: Integrating layered defense analysis...")
    logger.info("=" * 80)

    # Build edges from attack paths for SPOF detection
    edges = []
    for path in attack_paths:
        path_nodes = path.get("path", [])
        for i in range(len(path_nodes) - 1):
            edges.append((path_nodes[i], path_nodes[i+1]))

    # Generate layered defense recommendations
    from chatbot.modules.layered_defense import generate_layered_defense

    layered_defense = generate_layered_defense(
        attack_paths,
        nodes,
        edges,
        list(present_controls),
        rapids
    )

    # Merge layered defense recommendations with RAPIDS recommendations
    # Priority: RAPIDS (breadth) + Layered (depth) + SPOF (resilience)
    hop_recs = layered_defense.get("recommendations", [])

    logger.info(f"Layered defense generated {len(hop_recs)} hop-level recommendations")
    logger.info(f"Identified {len(layered_defense.get('spofs', []))} SPOFs")

    # Merge hop recommendations with RAPIDS recommendations
    # Strategy: Enrich RAPIDS recs with hop placement, add unique hop recs
    existing_control_map = {r["control"]: r for r in results}

    for hop_rec in hop_recs:
        control = hop_rec["control"]

        if control in existing_control_map:
            # ENRICH existing RAPIDS recommendation with hop placement data
            existing = existing_control_map[control]

            # Add hop-specific fields if not already present
            if "layer" not in existing or not existing.get("layer"):
                existing["layer"] = hop_rec.get("layer", "unknown")
            if "placement" not in existing or not existing.get("placement"):
                existing["placement"] = hop_rec.get("placement", "architecture")
            if "control_type" not in existing or not existing.get("control_type"):
                existing["control_type"] = hop_rec.get("control_type", "UNKNOWN")
            if "dir_category" not in existing or not existing.get("dir_category"):
                existing["dir_category"] = hop_rec.get("dir_category", "unknown")

            # Append hop-specific rationale
            hop_rationale = f"Depth: {hop_rec.get('control_type', 'control')} at {hop_rec.get('layer', 'unknown')} layer ({hop_rec.get('placement', 'hop')})"
            if hop_rationale not in existing.get("detailed_rationale", []):
                if isinstance(existing.get("detailed_rationale"), list):
                    existing["detailed_rationale"].append(hop_rationale)

        elif control not in present_controls:
            # ADD new hop recommendation (not in RAPIDS list)
            control_type = hop_rec.get("control_type", "UNKNOWN")
            dir_category = hop_rec.get("dir_category", "unknown")

            results.append({
                "control": control,
                "priority": hop_rec.get("priority", "high"),
                "score": 5.0,  # Lower than RAPIDS-driven, but still recommended
                "rapids_threats": [],
                "rapids_risk_score": 0,
                "mitigations": [],
                "techniques": [],
                "attack_paths": [],
                "rationale": f"Depth: {control_type} at {hop_rec.get('layer', 'unknown')} layer",
                "detailed_rationale": [f"{hop_rec.get('category', 'security')} control for {hop_rec.get('placement', 'architecture')}"],
                "category": hop_rec.get("category", "security"),
                "layer": hop_rec.get("layer", "unknown"),
                "placement": hop_rec.get("placement", "architecture"),
                "control_type": control_type,
                "dir_category": dir_category
            })
            existing_control_map[control] = results[-1]

    # Re-sort with hop recommendations included
    results.sort(key=lambda x: (-x["score"], -x["rapids_risk_score"]))

    # Add confidence scores
    results_with_confidence = add_confidence_to_recommendations(
        results,
        attack_paths,
        nodes,
        rapids,
        architecture_type
    )

    # Log final recommendations with Prevention vs Mitigation labels
    logger.info("Final RAPIDS-driven + Layered Defense recommendations:")
    logger.info("=" * 80)
    for i, rec in enumerate(results_with_confidence[:max_recommendations], 1):
        conf = rec.get("confidence", {})

        # Phase 3B-2: Show Prevention vs Mitigation (DIR)
        control_type_label = ""
        if rec.get("control_type"):
            control_type_label = f" [{rec['control_type']}]"
        elif rec.get("category") == "resilience":
            control_type_label = " [RESILIENCE]"

        logger.info(f"{i}. {rec['control'].upper()}{control_type_label} ({rec['priority']}, score={rec['score']:.1f}, confidence={conf.get('level', 'N/A')} {conf.get('score', 0):.0%})")
        if rec.get('rapids_threats'):
            logger.info(f"   RAPIDS: {', '.join(rec['rapids_threats'])}")
        if rec.get('attack_paths'):
            logger.info(f"   Evidence: {len(rec['attack_paths'])} attack path(s)")
        if rec.get('techniques'):
            logger.info(f"   MITRE: {len(rec['techniques'])} technique(s), {len(rec.get('mitigations', []))} mitigation(s)")
        if rec.get('layer'):
            logger.info(f"   Layer: {rec['layer']}")

    logger.info("=" * 80)

    # Attach layered defense metadata
    return_data = results_with_confidence[:max_recommendations]
    for rec in return_data:
        rec["_layered_defense"] = {
            "hop_analysis": layered_defense.get("hop_analysis", []),
            "spofs": layered_defense.get("spofs", [])
        }

    return return_data
