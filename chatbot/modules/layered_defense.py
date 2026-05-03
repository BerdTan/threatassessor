"""
Layered Defense Module: Hop-Based DDIR + Resilience Assessment

Phase 3B-2: Implements defense-in-depth and resilience by design.

Key Functions:
- categorize_hop_layer(): Identify layer type (identity/network/device/application/data)
- assess_hop_security_coverage(): Check security controls (Prevention + DIR mitigation)
- assess_hop_resilience(): Check resilience controls (availability DDIR)
- identify_single_points_of_failure(): SPOF detection from graph topology
- classify_entry_exposure(): Detect ambiguous entries (external/internal/ambiguous)
- generate_layered_defense(): Main function, returns hop-by-hop recommendations
"""

import logging
from typing import Dict, List, Set, Tuple, Optional

logger = logging.getLogger(__name__)


# ============================================================================
# LAYER CATEGORIZATION (By Node Descriptor, Not Position)
# ============================================================================

LAYER_KEYWORDS = {
    "identity": ["user", "admin", "auth", "sso", "mfa", "login", "identity", "iam"],
    "network": ["gateway", "router", "firewall", "load balancer", "proxy", "cdn", "waf"],
    "device": ["workstation", "server", "iot", "mobile", "endpoint", "device"],
    "application": ["web", "api", "service", "app", "orchestrator", "worker", "llm", "agent", "tool"],
    "data": ["database", "storage", "file", "s3", "blob", "vector", "cache", "db", "redis", "postgres"]
}


def categorize_hop_layer(node_label: str) -> str:
    """
    Categorize node by what it represents, not position in path.

    Args:
        node_label: Node label from architecture diagram

    Returns:
        Layer type: identity/network/device/application/data/unknown
    """
    label_lower = node_label.lower()

    for layer, keywords in LAYER_KEYWORDS.items():
        if any(kw in label_lower for kw in keywords):
            return layer

    return "unknown"


# ============================================================================
# ENTRY EXPOSURE CLASSIFICATION (Dual-Scenario Support)
# ============================================================================

def classify_entry_exposure(entry_label: str) -> str:
    """
    Classify entry point as external, internal, or ambiguous.

    Args:
        entry_label: Entry node label from architecture

    Returns:
        "external" - Clearly internet-facing
        "internal" - Clearly insider/authenticated
        "ambiguous" - Could be either (requires dual-scenario assessment)
    """
    label_lower = entry_label.lower()

    # Clearly external (internet-facing)
    if any(kw in label_lower for kw in ["internet", "public", "external", "web"]):
        return "external"

    # Clearly internal (insider/authenticated)
    if any(kw in label_lower for kw in ["employee", "admin", "staff", "internal"]):
        return "internal"

    # Ambiguous (could be either)
    if any(kw in label_lower for kw in ["user", "client", "customer", "mobile"]):
        return "ambiguous"

    # Default: Assume external (conservative risk-based approach)
    return "external"


# ============================================================================
# SECURITY ASSESSMENT: Prevention + Mitigation (DIR)
# ============================================================================
#
# Framework (docs/PREVENTION_VS_MITIGATION.md):
# - PREVENTION (40%): Controls that STOP attack path advancement
#   - If successful: Attack ENDS at this hop ✋
#   - Examples: WAF blocks exploit, MFA stops credential theft
#
# - MITIGATION (60%): Assume prevention FAILED (DIR = Detect, Isolate, Respond)
#   - DETECT (30%): Know attack is happening (Logging, IDS, SIEM)
#   - ISOLATE (20%): Contain the breach (Network Seg, Least Privilege)
#   - RESPOND (10%): Recover from impact (Backup, Incident Response)
#
# Each hop needs BOTH prevention AND mitigation (defense-in-depth)
# ============================================================================

# Layer-specific control mapping
LAYER_SECURITY_CONTROLS = {
    "identity": {
        "prevention": ["mfa", "sso", "password policy", "account lockout"],  # STOP credential theft
        "detect": ["login monitoring", "behavioral analysis", "anomaly detection", "logging"],  # Assume MFA bypassed
        "isolate": ["least privilege", "rbac", "session timeout", "account suspension"],  # Contain compromised account
        "respond": ["password reset", "account recovery", "incident response", "audit log"]  # Recover from breach
    },
    "network": {
        "prevention": ["firewall", "waf", "ddos protection", "network segmentation"],  # STOP connection
        "detect": ["ids", "network monitoring", "traffic analysis", "logging"],  # Assume firewall bypassed
        "isolate": ["vlan", "dmz", "network segmentation", "acl"],  # Contain lateral movement
        "respond": ["ip blocking", "traffic filtering", "incident response", "packet capture"]  # Recover
    },
    "device": {
        "prevention": ["edr", "antivirus", "patch management", "device hardening"],  # STOP malware
        "detect": ["edr", "host monitoring", "file integrity monitoring", "logging"],  # Assume malware executed
        "isolate": ["network segmentation", "quarantine", "device lockdown", "container isolation"],  # Contain infection
        "respond": ["device reimaging", "backup restore", "incident response", "forensics"]  # Recover
    },
    "application": {
        "prevention": ["input validation", "waf", "api gateway", "rate limiting"],  # STOP injection
        "detect": ["application logging", "error monitoring", "apm", "siem"],  # Assume injection succeeded
        "isolate": ["least privilege", "network segmentation", "container isolation", "circuit breaker"],  # Contain damage
        "respond": ["auto-rollback", "circuit breaker", "incident response", "patch deployment"]  # Recover
    },
    "data": {
        "prevention": ["encryption", "database firewall", "access control", "data masking"],  # STOP unauthorized query
        "detect": ["audit logging", "dlp", "query monitoring", "anomaly detection"],  # Assume query executed
        "isolate": ["least privilege", "column-level encryption", "data classification", "backup isolation"],  # Limit exposure
        "respond": ["backup restore", "data recovery", "incident response", "forensics"]  # Recover
    }
}


def assess_hop_security_coverage(
    node_label: str,
    layer: str,
    present_controls: List[str]
) -> Dict[str, bool]:
    """
    Check security coverage for a given hop: Prevention + Mitigation (DIR).

    Prevention (40%): Controls that STOP attack path at this hop
    Mitigation (60%): Assume prevention failed (Detect 30%, Isolate 20%, Respond 10%)

    Args:
        node_label: Node label for context
        layer: Layer type (identity/network/device/application/data)
        present_controls: List of controls already present in architecture

    Returns:
        Dict with coverage status: {"prevention": bool, "detect": bool, "isolate": bool, "respond": bool}
        - prevention: True if hop has controls that STOP attack
        - detect/isolate/respond: True if hop has mitigation when prevention fails
    """
    controls_lower = [c.lower() for c in present_controls]

    # Get layer-specific control expectations
    layer_controls = LAYER_SECURITY_CONTROLS.get(layer, {})

    coverage = {
        "prevention": False,  # Controls that STOP attack
        "detect": False,      # Mitigation: Know attack happening
        "isolate": False,     # Mitigation: Contain breach
        "respond": False      # Mitigation: Recover from impact
    }

    for category, expected_controls in layer_controls.items():
        # Check if any expected control is present
        coverage[category] = any(
            ec in " ".join(controls_lower) for ec in expected_controls
        )

    return coverage


# ============================================================================
# RESILIENCE ASSESSMENT: Prevention + Mitigation (DIR) for Availability
# ============================================================================
#
# Same framework applied to availability/resilience threats:
# - PREVENTION (40%): Controls that STOP DoS/resource exhaustion
# - MITIGATION (60%): Assume prevention failed (Detect, Isolate, Respond)
#
# Focus: Internal DoS, SPOF mitigation, cascading failure prevention
# ============================================================================

RESILIENCE_CONTROLS = {
    "prevention": [  # STOP DoS/resource exhaustion
        "rate limiting", "resource quotas", "connection pooling",
        "load balancer", "throttling", "queue management"
    ],
    "detect": [  # Assume DoS happening
        "health checks", "resource monitoring", "latency monitoring",
        "error rate alerting", "performance monitoring", "apm"
    ],
    "isolate": [  # Contain cascading failure
        "circuit breaker", "bulkhead pattern", "timeout policies",
        "queue management", "graceful degradation", "backpressure"
    ],
    "respond": [  # Recover availability
        "auto-scaling", "failover", "restart policies",
        "retry with backoff", "self-healing", "chaos engineering"
    ]
}


def assess_hop_resilience(
    node_label: str,
    layer: str,
    present_controls: List[str]
) -> Dict[str, bool]:
    """
    Check resilience coverage for a given hop: Prevention + Mitigation (DIR).

    Prevention (40%): Controls that STOP DoS/resource exhaustion
    Mitigation (60%): Assume prevention failed (Detect, Isolate, Respond)

    Focus: Internal DoS protection, SPOF mitigation, cascading failure prevention.

    Args:
        node_label: Node label for context
        layer: Layer type (for context)
        present_controls: List of controls already present

    Returns:
        Dict with resilience coverage: {"prevention": bool, "detect": bool, "isolate": bool, "respond": bool}
        - prevention: True if hop has controls that STOP DoS
        - detect/isolate/respond: True if hop has mitigation when prevention fails
    """
    controls_lower = [c.lower() for c in present_controls]

    coverage = {
        "prevention": False,  # Controls that STOP DoS
        "detect": False,      # Mitigation: Know DoS happening
        "isolate": False,     # Mitigation: Contain cascading failure
        "respond": False      # Mitigation: Recover availability
    }

    for category, expected_controls in RESILIENCE_CONTROLS.items():
        # Check if any resilience control is present
        coverage[category] = any(
            ec in " ".join(controls_lower) for ec in expected_controls
        )

    return coverage


# ============================================================================
# SPOF DETECTION (Graph Topology Analysis)
# ============================================================================

def identify_single_points_of_failure(
    nodes: Dict[str, Dict],
    edges: List[Tuple[str, str]]
) -> List[Dict]:
    """
    Identify single points of failure from graph topology.

    SPOF Indicators:
    1. Bottleneck: in-degree ≤ 1 AND out-degree ≥ 2
    2. Bridge: Removing node disconnects critical assets
    3. No redundancy: Single instance, no failover

    Args:
        nodes: Node dictionary from architecture
        edges: List of (source, target) tuples

    Returns:
        List of SPOF dicts with node_id, reason, and mitigation
    """
    spofs = []

    # Calculate in-degree and out-degree for each node
    in_degree = {node_id: 0 for node_id in nodes}
    out_degree = {node_id: 0 for node_id in nodes}

    for source, target in edges:
        if target in in_degree:
            in_degree[target] += 1
        if source in out_degree:
            out_degree[source] += 1

    for node_id, node_data in nodes.items():
        label = node_data.get("label", node_id)

        # Pattern 1: Bottleneck (single input, multiple outputs)
        if in_degree[node_id] <= 1 and out_degree[node_id] >= 2:
            spofs.append({
                "node_id": node_id,
                "label": label,
                "reason": "Bottleneck (single input, multiple outputs)",
                "in_degree": in_degree[node_id],
                "out_degree": out_degree[node_id],
                "mitigation": f"Load Balancer in front of {label}, 2+ instances, health checks"
            })

        # Pattern 2: Bridge (critical intermediary)
        # Simplified: Any node with in-degree ≥ 2 and out-degree ≥ 2 is a potential bridge
        elif in_degree[node_id] >= 2 and out_degree[node_id] >= 2:
            spofs.append({
                "node_id": node_id,
                "label": label,
                "reason": "Bridge node (critical intermediary)",
                "in_degree": in_degree[node_id],
                "out_degree": out_degree[node_id],
                "mitigation": f"Redundant {label} instances with load balancing, failover configuration"
            })

    return spofs


# ============================================================================
# HOP RECOMMENDATION GENERATION
# ============================================================================

def generate_hop_recommendations(
    hop: Dict,
    security_gaps: Dict[str, bool],
    resilience_gaps: Dict[str, bool],
    layer: str,
    is_critical: bool
) -> List[Dict]:
    """
    Generate control recommendations for a specific hop based on gaps.

    Args:
        hop: Hop dictionary with source, target, path info
        security_gaps: Security coverage (True = covered, False = gap)
        resilience_gaps: Resilience coverage
        layer: Layer type (identity/network/device/application/data)
        is_critical: Whether this is a critical hop (entry/target)

    Returns:
        List of control recommendations with Prevention + DIR labeling
    """
    recommendations = []

    # Security: Prevention + Mitigation (DIR)
    layer_controls = LAYER_SECURITY_CONTROLS.get(layer, {})

    for category in ["prevention", "detect", "isolate", "respond"]:
        if not security_gaps.get(category, False):
            # Gap exists, recommend control
            expected_controls = layer_controls.get(category, [])
            if expected_controls:
                # Pick first expected control as recommendation
                control = expected_controls[0]

                # Label as PREVENTION or MITIGATION (DIR)
                control_type = "PREVENTION" if category == "prevention" else f"MITIGATION:{category.upper()}"

                recommendations.append({
                    "control": control,
                    "category": "security",
                    "control_type": control_type,  # NEW: PREVENTION or MITIGATION:DETECT/ISOLATE/RESPOND
                    "dir_category": category,  # prevention, detect, isolate, respond
                    "layer": layer,
                    "priority": "critical" if (is_critical and category == "prevention") else "high",
                    "placement": f"At {hop.get('target_label', 'unknown')} hop"
                })

    # Resilience: Prevention + Mitigation (DIR) for availability
    for category in ["prevention", "detect", "isolate", "respond"]:
        if not resilience_gaps.get(category, False):
            # Gap exists, recommend resilience control
            expected_controls = RESILIENCE_CONTROLS.get(category, [])
            if expected_controls:
                control = expected_controls[0]

                # Label as PREVENTION or MITIGATION (DIR)
                control_type = "PREVENTION" if category == "prevention" else f"MITIGATION:{category.upper()}"

                recommendations.append({
                    "control": control,
                    "category": "resilience",
                    "control_type": control_type,  # NEW: PREVENTION or MITIGATION:DETECT/ISOLATE/RESPOND
                    "dir_category": category,
                    "layer": layer,
                    "priority": "high",
                    "placement": f"At {hop.get('target_label', 'unknown')} hop"
                })

    return recommendations


# ============================================================================
# MAIN FUNCTION: GENERATE LAYERED DEFENSE
# ============================================================================

def generate_layered_defense(
    attack_paths: List[Dict],
    nodes: Dict[str, Dict],
    edges: List[Tuple[str, str]],
    present_controls: List[str],
    rapids: Dict
) -> Dict:
    """
    Generate hop-by-hop defense-in-depth recommendations.

    Phase 3B-2: Prevention + Mitigation (DIR) per hop + SPOF detection.

    Framework:
    - PREVENTION (40%): Controls that STOP attack path at each hop
    - MITIGATION (60%): Assume prevention failed (DIR = Detect, Isolate, Respond)

    Args:
        attack_paths: List of attack path dicts from ground truth
        nodes: Node dictionary from architecture
        edges: List of (source, target) tuples
        present_controls: Controls already present
        rapids: RAPIDS assessment for context

    Returns:
        Dict with:
        - hop_analysis: List of hop dicts with DDIR coverage
        - spofs: List of SPOF dicts
        - recommendations: List of control recommendations
    """
    logger.info("Phase 3B-2: Generating layered defense (DDIR + Resilience)...")

    # Identify SPOFs first
    spofs = identify_single_points_of_failure(nodes, edges)
    logger.info(f"Identified {len(spofs)} single points of failure")

    # Analyze each hop in attack paths
    hop_analysis = []
    all_recommendations = []

    for path_idx, path in enumerate(attack_paths[:5]):  # Top 5 paths
        path_hops = path.get("path", [])

        for hop_idx in range(len(path_hops) - 1):
            source_id = path_hops[hop_idx]
            target_id = path_hops[hop_idx + 1]

            source_label = nodes[source_id].get("label", source_id)
            target_label = nodes[target_id].get("label", target_id)

            # Categorize target layer
            target_layer = categorize_hop_layer(target_label)

            # Assess security DDIR coverage
            security_coverage = assess_hop_security_coverage(
                target_label, target_layer, present_controls
            )

            # Assess resilience DDIR coverage
            resilience_coverage = assess_hop_resilience(
                target_label, target_layer, present_controls
            )

            # Determine if critical hop (entry or target)
            is_critical = (hop_idx == 0 or hop_idx == len(path_hops) - 2)

            # Check if SPOF
            is_spof = any(spof["node_id"] == target_id for spof in spofs)

            hop_info = {
                "path_id": path_idx,
                "hop_id": hop_idx,
                "source_id": source_id,
                "target_id": target_id,
                "source_label": source_label,
                "target_label": target_label,
                "layer": target_layer,
                "security_coverage": security_coverage,
                "resilience_coverage": resilience_coverage,
                "is_critical": is_critical,
                "is_spof": is_spof
            }

            hop_analysis.append(hop_info)

            # Generate recommendations for this hop
            hop_recs = generate_hop_recommendations(
                hop_info,
                security_coverage,
                resilience_coverage,
                target_layer,
                is_critical
            )

            all_recommendations.extend(hop_recs)

    logger.info(f"Analyzed {len(hop_analysis)} hops across {len(attack_paths[:5])} paths")
    logger.info(f"Generated {len(all_recommendations)} hop-level recommendations")

    return {
        "hop_analysis": hop_analysis,
        "spofs": spofs,
        "recommendations": all_recommendations
    }
