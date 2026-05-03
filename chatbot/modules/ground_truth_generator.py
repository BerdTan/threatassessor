"""
Ground Truth Generator - Architecture Security Validator

Generates validated ground truth labels for architecture diagrams using:
1. Deterministic parser (no LLM dependency, crowdsource-ready)
2. Control detection engine (keyword-based security control identification)
3. Attack path detection (graph-based path finding)
4. RAPIDS risk assessment (6 threat categories)
5. Optional LLM enhancement (attack narratives, missing controls)

This module is the foundation for validating our threat modeling engine
against real architectures and demonstrating robustness vs blind LLM usage.

Usage:
    # Parser-only (deterministic, no API key)
    truth = generate_ground_truth("architecture.mmd", use_llm=False)

    # LLM-enhanced (when API available)
    truth = generate_ground_truth("architecture.mmd", use_llm=True)
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from chatbot.parsers.mermaid_parser import parse_mermaid_file, MermaidParser
from tests.data.architectures.control_detection import (
    detect_controls_in_architecture,
    identify_missing_controls,
    calculate_control_coverage,
    map_controls_to_mitigations
)
from chatbot.modules.scoring import (
    score_technique,
    score_mitigation,
    calculate_composite_score
)
from chatbot.modules.threat_driven_controls import extract_control_names
from chatbot.modules.rapids_driven_controls import generate_rapids_driven_controls
from chatbot.modules.self_validation import (
    run_self_validation,
    apply_confidence_adjustments
)

logger = logging.getLogger(__name__)


# ============================================================================
# ARCHITECTURE TYPE DETECTION
# ============================================================================

def detect_architecture_type(nodes: List[Dict], edges: List[Dict], subgraphs: List[Dict]) -> str:
    """
    Detect architecture type from components.

    Returns: "web_app", "cloud", "ai_system", "iot", "generic"
    """
    node_labels_lower = " ".join([n.get("label", "").lower() for n in nodes])

    # AI/LLM system indicators
    ai_keywords = ["llm", "agent", "vector", "embedding", "prompt", "openai", "claude", "gpt"]
    if any(kw in node_labels_lower for kw in ai_keywords):
        return "ai_system"

    # Web application indicators
    web_keywords = ["web server", "load balancer", "waf", "alb", "nginx", "apache"]
    if any(kw in node_labels_lower for kw in web_keywords):
        return "web_app"

    # Cloud indicators
    cloud_keywords = ["vpc", "subnet", "s3", "lambda", "azure", "gcp", "aws"]
    if any(kw in node_labels_lower for kw in cloud_keywords):
        return "cloud"

    # IoT indicators
    iot_keywords = ["sensor", "device", "gateway", "mqtt", "iot"]
    if any(kw in node_labels_lower for kw in iot_keywords):
        return "iot"

    return "generic"


# ============================================================================
# ATTACK PATH DETECTION (Graph Analysis + Keywords)
# ============================================================================

def calculate_node_degrees(edges: List[Dict]) -> Tuple[Dict[str, int], Dict[str, int]]:
    """Calculate in-degree and out-degree for all nodes."""
    in_degree = {}
    out_degree = {}

    for edge in edges:
        source = edge.get("source")
        target = edge.get("target")

        if source:
            out_degree[source] = out_degree.get(source, 0) + 1
            in_degree.setdefault(source, 0)

        if target:
            in_degree[target] = in_degree.get(target, 0) + 1
            out_degree.setdefault(target, 0)

    return in_degree, out_degree


def find_entry_points(nodes: Dict[str, Dict], edges: List[Dict] = None) -> List[str]:
    """
    Find entry points using graph analysis + keywords.

    Entry points are:
    1. External sources (Internet, Public) - HIGH confidence
    2. Zero in-degree nodes (graph sources) - MEDIUM confidence
    3. User/workstation nodes (lateral entry) - MEDIUM confidence
    """
    entry_points = []

    # High-confidence keywords (external entry)
    high_keywords = ["internet", "external", "public", "attacker"]

    # Medium-confidence keywords (lateral entry / compromised)
    medium_keywords = ["user", "workstation", "laptop", "endpoint", "desktop", "client", "mobile"]

    # Also check for web servers as potential entry (internal pivot)
    pivot_keywords = ["web server", "webserver", "web app", "webapp", "api", "portal"]

    # Calculate graph structure if edges provided
    in_degree = {}
    if edges:
        in_degree, _ = calculate_node_degrees(edges)

    for node_id, node_data in nodes.items():
        label_lower = node_data.get("label", node_id).lower()

        # High-confidence: External entry points
        if any(kw in label_lower for kw in high_keywords):
            entry_points.append(node_id)
            logger.debug(f"Entry point (external): {node_id}")

        # Medium-confidence: User/endpoint (lateral movement)
        elif any(kw in label_lower for kw in medium_keywords):
            entry_points.append(node_id)
            logger.debug(f"Entry point (lateral): {node_id}")

        # Medium-confidence: Web servers (public-facing, can be entry)
        elif any(kw in label_lower for kw in pivot_keywords):
            entry_points.append(node_id)
            logger.debug(f"Entry point (pivot): {node_id}")

        # Graph-based: Zero in-degree (external source)
        elif edges and in_degree.get(node_id, 0) == 0:
            entry_points.append(node_id)
            logger.debug(f"Entry point (graph-source): {node_id}")

    return entry_points


def find_sensitive_targets(nodes: Dict[str, Dict], edges: List[Dict] = None) -> List[str]:
    """
    Find sensitive targets using graph analysis + keywords.

    Targets are prioritized:
    1. Data stores (Database, Secrets) - HIGH priority
    2. Execution environments (Code, Admin) - HIGH priority
    3. File storage (FileServer, Cache, S3) - MEDIUM priority
    4. Zero out-degree nodes (sinks) - LOW priority
    """
    targets = []

    # High-priority keywords (critical assets)
    high_priority = [
        "database", "db", "secret", "key", "credential",
        "admin", "root", "token", "pii", "payment",
        "code execution", "code exec", "exec", "command"
    ]

    # Medium-priority keywords (valuable assets)
    medium_priority = [
        "file server", "fileserver", "file", "storage", "s3", "bucket",
        "cache", "backup", "data", "document", "vector",
        "api key", "config", "tool"
    ]

    # Calculate graph structure if edges provided
    out_degree = {}
    if edges:
        _, out_degree = calculate_node_degrees(edges)

    for node_id, node_data in nodes.items():
        label_lower = node_data.get("label", node_id).lower()

        # High-priority: Critical data stores and execution
        if any(kw in label_lower for kw in high_priority):
            targets.append(node_id)
            logger.debug(f"Target (high-priority): {node_id}")

        # Medium-priority: File storage and caches
        elif any(kw in label_lower for kw in medium_priority):
            targets.append(node_id)
            logger.debug(f"Target (medium-priority): {node_id}")

        # Graph-based: Zero out-degree (terminal nodes / sinks)
        elif edges and out_degree.get(node_id, 0) == 0:
            # Only add if not already identified and looks like a meaningful target
            if node_id not in targets:
                # Filter out obvious non-targets (load balancers, proxies, gateways)
                if not any(kw in label_lower for kw in ["load balancer", "proxy", "gateway", "router", "firewall"]):
                    targets.append(node_id)
                    logger.debug(f"Target (graph-sink): {node_id}")

    return targets


def find_attack_paths_bfs(
    parser: MermaidParser,
    entry_points: List[str],
    targets: List[str],
    max_paths: int = 10,  # Increased from 5 to 10
    max_path_length: int = 8  # Limit path length to avoid cycles
) -> List[Dict]:
    """
    Find attack paths using BFS from entry points to sensitive targets.

    Finds multiple paths per entry-target pair (up to 2 paths each).

    Returns list of attack path dicts with:
        - id: AP-{n}
        - entry: Entry point node ID
        - target: Target node ID
        - path: List of node IDs from entry to target
        - hop_count: Number of hops
    """
    adjacency = parser.get_adjacency_list()
    attack_paths = []
    path_id = 1

    for entry in entry_points:
        if entry not in adjacency:
            # Check if entry has outgoing edges
            has_outgoing = any(entry == edge.get("source") for edge in parser.edges)
            if not has_outgoing:
                logger.debug(f"Skipping entry {entry} - no outgoing edges")
                continue

        for target in targets:
            if entry == target:
                continue

            # Find up to 2 paths per entry-target pair
            paths_found = 0
            max_per_pair = 2

            # BFS to find shortest paths (multiple)
            queue = [(entry, [entry])]
            visited_paths = set()

            while queue and paths_found < max_per_pair and len(attack_paths) < max_paths:
                current, path = queue.pop(0)

                # Skip if path too long (avoid cycles)
                if len(path) > max_path_length:
                    continue

                if current == target:
                    # Found path to target
                    path_tuple = tuple(path)
                    if path_tuple not in visited_paths:
                        visited_paths.add(path_tuple)
                        attack_paths.append({
                            "id": f"AP-{path_id}",
                            "entry": entry,
                            "target": target,
                            "path": path,
                            "hop_count": len(path) - 1
                        })
                        path_id += 1
                        paths_found += 1
                    continue

                # Explore neighbors
                for neighbor in adjacency.get(current, []):
                    if neighbor not in path:  # Avoid cycles within path
                        queue.append((neighbor, path + [neighbor]))

            if len(attack_paths) >= max_paths:
                break

        if len(attack_paths) >= max_paths:
            break

    return attack_paths


def calculate_path_criticality(
    attack_path: Dict,
    nodes: Dict[str, Dict],
    controls_present: List[str],
    all_edges: List[Dict]
) -> float:
    """
    Calculate criticality score for an attack path (0.0-1.0, higher = more critical).

    Factors:
    - Target sensitivity (database > file server > general)
    - Path length (shorter = more critical, easier to exploit)
    - Controls on path (fewer = more critical, less defended)
    - Entry point externality (internet > internal)
    """
    path = attack_path["path"]
    entry = attack_path["entry"]
    target = attack_path["target"]

    # Factor 1: Target sensitivity (0.0-1.0)
    target_label = nodes[target].get("label", "").lower()
    if any(kw in target_label for kw in ["database", "db", "secret", "credential"]):
        target_score = 1.0  # Critical
    elif any(kw in target_label for kw in ["admin", "root", "key", "token"]):
        target_score = 0.9  # High
    elif any(kw in target_label for kw in ["code execution", "exec", "command"]):
        target_score = 0.85  # High
    elif any(kw in target_label for kw in ["file", "storage", "cache"]):
        target_score = 0.6  # Medium
    else:
        target_score = 0.4  # Low

    # Factor 2: Path length (inverse - shorter is more critical)
    hop_count = attack_path["hop_count"]
    if hop_count == 1:
        path_length_score = 1.0  # Direct access
    elif hop_count == 2:
        path_length_score = 0.85
    elif hop_count <= 4:
        path_length_score = 0.7
    elif hop_count <= 6:
        path_length_score = 0.5
    else:
        path_length_score = 0.3  # Long path, less likely

    # Factor 3: Controls on path (fewer controls = more critical)
    controls_on_path = 0
    for node_id in path:
        node_label = nodes[node_id].get("label", "").lower()
        # Check if any control keyword appears in this node
        for control in controls_present:
            if control.replace("_", " ") in node_label:
                controls_on_path += 1
                break

    if controls_on_path == 0:
        control_score = 1.0  # No defenses
    elif controls_on_path == 1:
        control_score = 0.7  # Minimal defense
    elif controls_on_path == 2:
        control_score = 0.4  # Moderate defense
    else:
        control_score = 0.2  # Well-defended path

    # Factor 4: Entry point externality (external > internal)
    entry_label = nodes[entry].get("label", "").lower()
    if any(kw in entry_label for kw in ["internet", "public", "external"]):
        entry_score = 1.0  # External entry
    elif any(kw in entry_label for kw in ["user", "client", "workstation"]):
        entry_score = 0.8  # User entry (phishing, social eng)
    else:
        entry_score = 0.5  # Internal pivot

    # Weighted composite score
    criticality = (
        target_score * 0.35 +
        path_length_score * 0.25 +
        control_score * 0.25 +
        entry_score * 0.15
    )

    return round(criticality, 3)


def rank_and_deduplicate_paths(
    attack_paths: List[Dict],
    nodes: Dict[str, Dict],
    controls_present: List[str],
    edges: List[Dict],
    top_n: int = 5
) -> List[Dict]:
    """
    Rank attack paths by criticality and deduplicate similar patterns.

    Returns top-N most critical unique paths.
    """
    if not attack_paths:
        return []

    # Calculate criticality scores
    for ap in attack_paths:
        ap["criticality"] = calculate_path_criticality(ap, nodes, controls_present, edges)
        ap["criticality_tier"] = (
            "CRITICAL" if ap["criticality"] >= 0.8 else
            "HIGH" if ap["criticality"] >= 0.6 else
            "MEDIUM" if ap["criticality"] >= 0.4 else
            "LOW"
        )

    # Sort by criticality (descending)
    sorted_paths = sorted(attack_paths, key=lambda x: x["criticality"], reverse=True)

    # Deduplicate by pattern (same entry→target with similar hop count)
    unique_paths = []
    seen_patterns = set()

    for ap in sorted_paths:
        # Pattern: entry + target + hop_count_bucket
        hop_bucket = (ap["hop_count"] // 2) * 2  # Bucket: 0-1, 2-3, 4-5, etc
        pattern = (ap["entry"], ap["target"], hop_bucket)

        if pattern not in seen_patterns:
            seen_patterns.add(pattern)
            unique_paths.append(ap)

        if len(unique_paths) >= top_n:
            break

    logger.info(f"Ranked paths: {len(attack_paths)} total → {len(unique_paths)} unique top-{top_n}")

    return unique_paths


def map_path_to_techniques(
    path: List[str],
    nodes: Dict[str, Dict],
    controls_present: List[str]
) -> List[str]:
    """
    Map attack path to MITRE techniques based on components.

    Simple heuristic mapping (can be enhanced with LLM).
    """
    techniques = []

    # Entry point techniques
    entry_label = nodes[path[0]].get("label", "").lower()
    if "internet" in entry_label or "public" in entry_label:
        techniques.append("T1190")  # Exploit Public-Facing Application
    if "user" in entry_label:
        techniques.append("T1566")  # Phishing

    # Traversal techniques
    for node_id in path[1:-1]:
        label = nodes[node_id].get("label", "").lower()

        if "web" in label or "api" in label:
            techniques.append("T1190")  # Exploit Public-Facing Application
        if "server" in label or "application" in label:
            techniques.append("T1059")  # Command and Scripting Interpreter
        if "network" in label or "router" in label:
            techniques.append("T1090")  # Proxy

    # Target techniques
    target_label = nodes[path[-1]].get("label", "").lower()
    if "database" in target_label or "db" in target_label:
        techniques.append("T1213")  # Data from Information Repositories
    if "secret" in target_label or "key" in target_label:
        techniques.append("T1552")  # Unsecured Credentials

    # Control-based technique mapping
    if "waf" not in controls_present:
        techniques.append("T1190")  # Exploit Public-Facing Application
    if "mfa" not in controls_present:
        techniques.append("T1078")  # Valid Accounts

    # Deduplicate while preserving order
    seen = set()
    unique_techniques = []
    for t in techniques:
        if t not in seen:
            seen.add(t)
            unique_techniques.append(t)

    return unique_techniques[:5]  # Top 5


# ============================================================================
# RAPIDS RISK ASSESSMENT (Architecture-Type-Aware)
# ============================================================================

# Base risk scores by architecture type (context-aware baselines)
ARCHITECTURE_BASE_RISKS = {
    "web_app": {
        "ransomware": 50,           # Lower - less common target
        "application_vulns": 80,    # Higher - primary attack vector
        "phishing": 60,             # Standard
        "insider_threat": 50,       # Lower - less privileged access
        "dos": 70,                  # Higher - public-facing
        "supply_chain": 60          # Standard
    },
    "cloud": {
        "ransomware": 65,           # Higher - data at scale
        "application_vulns": 70,    # Standard
        "phishing": 65,             # Standard
        "insider_threat": 60,       # Standard
        "dos": 60,                  # Cloud has some built-in protection
        "supply_chain": 70          # Higher - many dependencies
    },
    "ai_system": {
        "ransomware": 40,           # Lower - not primary concern
        "application_vulns": 90,    # CRITICAL - prompt injection, model abuse
        "phishing": 70,             # Higher - social engineering LLM
        "insider_threat": 80,       # CRITICAL - data poisoning, model theft
        "dos": 85,                  # CRITICAL - API abuse, resource exhaustion
        "supply_chain": 75          # Higher - model/data provenance
    },
    "iot": {
        "ransomware": 75,           # Higher - hard to recover
        "application_vulns": 80,    # Higher - embedded firmware
        "phishing": 40,             # Lower - limited user interaction
        "insider_threat": 55,       # Standard
        "dos": 85,                  # CRITICAL - resource-constrained
        "supply_chain": 80          # CRITICAL - hardware/firmware supply chain
    },
    "generic": {
        "ransomware": 60,
        "application_vulns": 65,
        "phishing": 60,
        "insider_threat": 60,
        "dos": 65,
        "supply_chain": 60
    }
}


def get_base_risk(category: str, architecture_type: str) -> int:
    """Get context-aware base risk score."""
    return ARCHITECTURE_BASE_RISKS.get(architecture_type, ARCHITECTURE_BASE_RISKS["generic"]).get(category, 60)


def assess_rapids_risks(
    architecture_type: str,
    controls_present: List[str],
    attack_paths: List[Dict],
    nodes: Dict[str, Dict]
) -> Dict:
    """
    Calculate RAPIDS risk scores with architecture-type-aware baselines.

    Returns dict with 6 categories, each containing:
        - risk: 0-100 (higher = worse)
        - defensibility: 0-100 (higher = better protected)
        - rationale: Explanation
    """
    controls_set = set(controls_present)
    node_labels = " ".join([n.get("label", "").lower() for n in nodes.values()])

    # Ransomware risk (context-aware baseline)
    has_backup = "backup" in controls_set
    has_edr = "edr" in controls_set
    has_segmentation = "network segmentation" in controls_set

    ransomware_risk = get_base_risk("ransomware", architecture_type)
    ransomware_def = 20
    if not has_backup:
        ransomware_risk += 20
    else:
        ransomware_def += 30
    if has_edr:
        ransomware_def += 30
    if has_segmentation:
        ransomware_def += 20

    ransomware_rationale = f"Backup: {'✓' if has_backup else '✗'}, EDR: {'✓' if has_edr else '✗'}, Segmentation: {'✓' if has_segmentation else '✗'}"

    # Application vulnerabilities (AI-specific: prompt injection, model abuse)
    has_waf = "waf" in controls_set
    has_input_validation = "input validation" in controls_set
    has_rate_limiting = "rate limiting" in controls_set
    has_prompt_filtering = "prompt filtering" in controls_set
    has_output_filtering = "output filtering" in controls_set

    app_vuln_risk = get_base_risk("application_vulns", architecture_type)
    app_vuln_def = 10
    # AI-specific controls for application vulnerabilities
    if architecture_type == "ai_system":
        if has_prompt_filtering:
            app_vuln_def += 40
            app_vuln_risk -= 25
        if has_output_filtering:
            app_vuln_def += 20
            app_vuln_risk -= 15
        if has_input_validation:
            app_vuln_def += 15
        if has_rate_limiting:
            app_vuln_def += 15
        app_vuln_rationale = f"Prompt filter: {'✓' if has_prompt_filtering else '✗'}, Output filter: {'✓' if has_output_filtering else '✗'}, Input validation: {'✓' if has_input_validation else '✗'}, Rate limiting: {'✓' if has_rate_limiting else '✗'}"
    else:
        # Standard web/cloud controls
        if has_waf:
            app_vuln_def += 40
            app_vuln_risk -= 20
        if has_input_validation:
            app_vuln_def += 20
        if has_rate_limiting:
            app_vuln_def += 20
        app_vuln_rationale = f"WAF: {'✓' if has_waf else '✗'}, Input validation: {'✓' if has_input_validation else '✗'}, Rate limiting: {'✓' if has_rate_limiting else '✗'}"

    # Phishing risk (context-aware)
    has_mfa = "mfa" in controls_set
    has_email_gateway = "email" in node_labels

    phishing_risk = get_base_risk("phishing", architecture_type)
    phishing_def = 10
    if has_mfa:
        phishing_def += 50
        phishing_risk -= 30
    if has_email_gateway:
        phishing_def += 20

    phishing_rationale = f"MFA: {'✓' if has_mfa else '✗'}, Email gateway: {'✓' if has_email_gateway else '✗'}"

    # Insider threat (AI-specific: data poisoning, model theft)
    has_audit_log = "audit log" in controls_set or "logging" in controls_set
    has_least_privilege = "least privilege" in controls_set or "iam" in controls_set
    has_model_access_control = "model access control" in controls_set

    insider_risk = get_base_risk("insider_threat", architecture_type)
    insider_def = 20

    # AI-specific adjustments
    if architecture_type == "ai_system" and has_model_access_control:
        insider_def += 35
        insider_risk -= 20
    if has_audit_log:
        insider_def += 30
    if has_least_privilege:
        insider_def += 30
        insider_risk -= 20

    insider_rationale = f"Audit logging: {'✓' if has_audit_log else '✗'}, Least privilege: {'✓' if has_least_privilege else '✗'}"
    if architecture_type == "ai_system":
        insider_rationale += f", Model access control: {'✓' if has_model_access_control else '✗'}"

    # DoS risk (AI-specific: API abuse, resource exhaustion)
    has_load_balancer = "load balancer" in controls_set
    has_ddos_protection = "ddos protection" in controls_set

    dos_risk = get_base_risk("dos", architecture_type)
    dos_def = 10
    if has_load_balancer:
        dos_def += 30
        dos_risk -= 20
    if has_ddos_protection:
        dos_def += 40
        dos_risk -= 20

    dos_rationale = f"Load balancer: {'✓' if has_load_balancer else '✗'}, DDoS protection: {'✓' if has_ddos_protection else '✗'}"

    # Supply chain risk (AI-specific: model/data provenance)
    supply_chain_risk = get_base_risk("supply_chain", architecture_type)
    supply_chain_def = 30

    if architecture_type == "ai_system":
        supply_chain_rationale = "AI-specific: Model provenance, training data integrity, third-party APIs. Requires validation of LLM providers and data sources."
    else:
        supply_chain_rationale = "Requires manual assessment of dependencies and third-party integrations"

    return {
        "ransomware": {
            "risk": min(ransomware_risk, 100),
            "defensibility": min(ransomware_def, 100),
            "rationale": ransomware_rationale
        },
        "application_vulns": {
            "risk": min(app_vuln_risk, 100),
            "defensibility": min(app_vuln_def, 100),
            "rationale": app_vuln_rationale
        },
        "phishing": {
            "risk": min(phishing_risk, 100),
            "defensibility": min(phishing_def, 100),
            "rationale": phishing_rationale
        },
        "insider_threat": {
            "risk": min(insider_risk, 100),
            "defensibility": min(insider_def, 100),
            "rationale": insider_rationale
        },
        "dos": {
            "risk": min(dos_risk, 100),
            "defensibility": min(dos_def, 100),
            "rationale": dos_rationale
        },
        "supply_chain": {
            "risk": supply_chain_risk,
            "defensibility": supply_chain_def,
            "rationale": supply_chain_rationale
        }
    }


# ============================================================================
# OVERALL RISK SCORING (Defense-in-Depth)
# ============================================================================

# Control tier categorization for defense-in-depth scoring
CONTROL_TIERS = {
    "critical": [
        "waf", "mfa", "edr", "network segmentation", "backup",
        "ddos protection", "ids/ips", "prompt filtering", "sandbox"
    ],
    "high": [
        "firewall", "encryption at rest", "encryption in transit",
        "siem", "least privilege", "iam", "input validation",
        "api gateway", "secrets management"
    ],
    "medium": [
        "logging", "audit log", "load balancer", "rate limiting",
        "vpn", "reverse proxy", "output filtering", "antivirus"
    ],
    "low": [
        "monitoring", "cache", "message queue", "database replication",
        "cdn", "service mesh"
    ]
}


def calculate_defense_in_depth_score(controls_present: List[str]) -> float:
    """
    Calculate defense-in-depth score based on control tier diversity.

    Returns:
        0.0 = no controls
        0.3 = single tier
        0.6 = two tiers
        0.9 = three+ tiers with critical controls
        1.0 = exceptional (all tiers, multiple critical)
    """
    if not controls_present:
        return 0.0

    tiers_present = set()
    critical_count = 0
    high_count = 0

    for control in controls_present:
        for tier, tier_controls in CONTROL_TIERS.items():
            if control in tier_controls:
                tiers_present.add(tier)
                if tier == "critical":
                    critical_count += 1
                elif tier == "high":
                    high_count += 1
                break

    # Base score from tier diversity (0.2 per tier, max 0.8)
    tier_score = len(tiers_present) * 0.2

    # Bonus for critical controls (0.1 each, max +0.3)
    critical_bonus = min(critical_count * 0.1, 0.3)

    # Small bonus for multiple high-tier controls
    high_bonus = min(high_count * 0.02, 0.1)

    total = min(tier_score + critical_bonus + high_bonus, 1.0)

    logger.debug(f"Defense-in-depth: {total:.2f} (tiers: {len(tiers_present)}, critical: {critical_count}, high: {high_count})")

    return total


def calculate_overall_risk_score(
    rapids_assessment: Dict,
    attack_path_count: int,
    control_coverage: float,
    controls_present: List[str]
) -> int:
    """
    Calculate overall risk score (0-100, higher = worse).

    Factors:
    - RAPIDS average risk (baseline)
    - Defense-in-depth score (major risk reduction)
    - Attack path count (moderate risk increase)
    - Control coverage (minor risk adjustment)
    """
    # Average RAPIDS risk (baseline threat level)
    rapids_risks = [cat["risk"] for cat in rapids_assessment.values()]
    avg_rapids_risk = sum(rapids_risks) / len(rapids_risks)

    # Defense-in-depth modifier (MAJOR impact)
    did_score = calculate_defense_in_depth_score(controls_present)
    did_reduction = did_score * 40  # Up to -40 points for strong defense

    # Attack path contribution (reduced weight - good defenses mitigate paths)
    path_risk_modifier = min(attack_path_count * 3, 15)  # Reduced from 5→3, cap 15

    # Control coverage (minor adjustment)
    coverage_risk_modifier = (1.0 - control_coverage) * 20  # Reduced from 30→20

    overall_risk = avg_rapids_risk + path_risk_modifier + coverage_risk_modifier - did_reduction

    # Clamp to [5, 100] - minimum 5 (always some residual risk)
    return max(5, min(int(overall_risk), 100))


def calculate_overall_defensibility(
    rapids_assessment: Dict,
    control_coverage: float,
    controls_present: List[str]
) -> int:
    """
    Calculate overall defensibility score (0-100, higher = better).
    """
    # Average RAPIDS defensibility
    rapids_def = [cat["defensibility"] for cat in rapids_assessment.values()]
    avg_rapids_def = sum(rapids_def) / len(rapids_def)

    # Defense-in-depth bonus (MAJOR impact)
    did_score = calculate_defense_in_depth_score(controls_present)
    did_bonus = did_score * 35  # Up to +35 points

    # Control coverage contribution
    coverage_bonus = control_coverage * 15  # Reduced from 30→15 (less important than quality)

    overall_def = avg_rapids_def + did_bonus + coverage_bonus

    return min(int(overall_def), 100)


# ============================================================================
# MAIN GENERATION FUNCTION
# ============================================================================

def generate_ground_truth(
    mmd_file_path: str,
    use_llm: bool = False,
    llm_model: Optional[str] = None
) -> Dict:
    """
    Generate ground truth labels from architecture diagram.

    Args:
        mmd_file_path: Path to .mmd architecture file
        use_llm: Whether to use LLM for enhancement (default: False)
        llm_model: Optional LLM model override (default: uses agentic.llm default)

    Returns:
        Ground truth dict with schema:
        {
            "architecture": "filename.mmd",
            "description": "...",
            "controls_present": [...],
            "controls_missing": [...],
            "expected_attack_paths": [...],
            "expected_risk_score": 0-100,
            "expected_defensibility": 0-100,
            "rapids_assessment": {...},
            "rationale": "...",
            "metadata": {
                "generated_by": "parser" | "parser+llm",
                "architecture_type": "web_app" | "cloud" | "ai_system" | ...,
                "node_count": N,
                "edge_count": M
            }
        }
    """
    logger.info(f"Generating ground truth for {mmd_file_path} (LLM: {use_llm})")

    # Parse architecture
    parsed = parse_mermaid_file(mmd_file_path)
    parser = MermaidParser()
    with open(mmd_file_path, 'r') as f:
        parser.parse(f.read())

    # Convert to list format
    nodes_list = [
        {"id": node_id, "label": node_data.get("label", node_id)}
        for node_id, node_data in parsed["nodes"].items()
    ]
    edges_list = [
        {"source": edge["source"], "target": edge["target"], "label": edge.get("label") or ""}
        for edge in parsed["edges"]
    ]
    subgraphs_list = [
        {"id": sg_id, "label": sg_data.get("display_name", sg_id)}
        for sg_id, sg_data in parsed.get("subgraphs", {}).items()
    ]

    # Detect architecture type
    arch_type = detect_architecture_type(nodes_list, edges_list, subgraphs_list)
    logger.info(f"Detected architecture type: {arch_type}")

    # Detect controls
    control_result = detect_controls_in_architecture(nodes_list, edges_list, subgraphs_list)
    controls_present = control_result["controls_present"]
    logger.info(f"Detected {len(controls_present)} controls: {controls_present}")

    # Identify missing controls
    controls_missing = identify_missing_controls(arch_type, controls_present)
    controls_missing_names = [c["control"] for c in controls_missing]

    # Calculate control coverage
    coverage = calculate_control_coverage(controls_present, arch_type)
    logger.info(f"Control coverage: {coverage:.1%}")

    # Find attack paths (pass edges for graph analysis)
    entry_points = find_entry_points(parsed["nodes"], parsed["edges"])
    targets = find_sensitive_targets(parsed["nodes"], parsed["edges"])
    logger.info(f"Detected {len(entry_points)} entry points: {entry_points}")
    logger.info(f"Detected {len(targets)} targets: {targets}")
    attack_paths_raw = find_attack_paths_bfs(parser, entry_points, targets, max_paths=15)
    logger.info(f"Found {len(attack_paths_raw)} raw attack paths")

    # Rank and deduplicate paths (keep top 5 most critical)
    attack_paths = rank_and_deduplicate_paths(
        attack_paths_raw,
        parsed["nodes"],
        controls_present,
        parsed["edges"],
        top_n=5
    )
    logger.info(f"After ranking: {len(attack_paths)} critical paths")

    # Enrich attack paths with techniques and enhanced rationale
    for ap in attack_paths:
        ap["techniques"] = map_path_to_techniques(
            ap["path"],
            parsed["nodes"],
            controls_present
        )

        # Enhanced rationale with criticality
        tier = ap["criticality_tier"]
        path_str = " → ".join([parsed["nodes"][n].get("label", n) for n in ap["path"]])
        ap["rationale"] = f"[{tier}] {path_str}: {ap['hop_count']} hop{'s' if ap['hop_count'] != 1 else ''}, criticality score {ap['criticality']:.2f}"

    # RAPIDS assessment
    rapids_assessment = assess_rapids_risks(
        arch_type,
        controls_present,
        attack_paths,
        parsed["nodes"]
    )

    # Overall scores (with defense-in-depth consideration)
    risk_score = calculate_overall_risk_score(rapids_assessment, len(attack_paths), coverage, controls_present)
    defensibility_score = calculate_overall_defensibility(rapids_assessment, coverage, controls_present)

    # Generate rationale
    if len(controls_present) == 0:
        posture = "No security controls detected - highly vulnerable"
    elif coverage < 0.3:
        posture = "Minimal security controls - significant gaps"
    elif coverage < 0.6:
        posture = "Some security controls - moderate protection"
    elif coverage < 0.8:
        posture = "Good security controls - defense-in-depth"
    else:
        posture = "Strong security posture - comprehensive controls"

    rationale = f"{posture}. {len(attack_paths)} attack paths identified. Control coverage: {coverage:.0%}."

    # Prepare partial ground truth for threat-driven recommendations
    partial_ground_truth = {
        "expected_attack_paths": attack_paths,
        "rapids_assessment": rapids_assessment,
    }

    # RAPIDS-DRIVEN CONTROL RECOMMENDATIONS (Primary: RAPIDS threats, Secondary: MITRE validation)
    # This generates controls based on RAPIDS threat assessment, validated by attack paths
    # RAPIDS = PRIMARY driver (what threats exist?), Attack Paths = EVIDENCE (how are they exploitable?)
    control_recommendations = generate_rapids_driven_controls(
        partial_ground_truth,
        set(controls_present),
        parsed["nodes"],
        arch_type,
        max_recommendations=6
    )
    controls_missing_names = extract_control_names(control_recommendations)
    logger.info(f"Threat-driven recommendations: {controls_missing_names}")

    # Build initial ground truth
    ground_truth = {
        "architecture": Path(mmd_file_path).name,
        "description": f"{arch_type.replace('_', ' ').title()} architecture",
        "controls_present": controls_present,
        "controls_missing": controls_missing_names,
        "control_recommendations": control_recommendations,  # Full details with confidence
        "expected_attack_paths": attack_paths,
        "expected_risk_score": risk_score,
        "expected_defensibility": defensibility_score,
        "rapids_assessment": rapids_assessment,
        "rationale": rationale,
        "metadata": {
            "generated_by": "parser+llm" if use_llm else "parser",
            "architecture_type": arch_type,
            "node_count": len(parsed["nodes"]),
            "edge_count": len(parsed["edges"]),
            "control_coverage": round(coverage, 2)
        }
    }

    # SELF-VALIDATION: Check technique relevance, RAPIDS alignment, control mappings
    # This adjusts confidence scores based on validation results
    logger.info("\n")
    validation_report = run_self_validation(ground_truth, parsed["nodes"], arch_type)

    # Apply confidence adjustments from validation
    adjusted_recommendations = apply_confidence_adjustments(
        control_recommendations,
        validation_report
    )
    ground_truth["control_recommendations"] = adjusted_recommendations
    ground_truth["validation_report"] = validation_report

    # Update controls_missing with potentially re-prioritized list
    controls_missing_names = extract_control_names(adjusted_recommendations)
    ground_truth["controls_missing"] = controls_missing_names

    # LLM enhancement (if requested and available)
    if use_llm:
        try:
            ground_truth = enhance_with_llm(ground_truth, mmd_file_path, llm_model)
        except Exception as e:
            logger.warning(f"LLM enhancement failed: {e}, using parser-only result")

    return ground_truth


def enhance_with_llm(
    parser_truth: Dict,
    mmd_file_path: str,
    llm_model: Optional[str] = None
) -> Dict:
    """
    Enhance parser-generated ground truth with LLM analysis.

    LLM adds:
    - Better attack path rationales
    - More specific missing control recommendations
    - Improved overall description and rationale
    """
    from agentic.llm import generate_response_with_system

    with open(mmd_file_path, 'r') as f:
        mermaid_content = f.read()

    system_prompt = "You are a cybersecurity architect specializing in threat modeling and MITRE ATT&CK framework."

    user_prompt = f"""
Enhance this architecture security assessment with specific rationales and recommendations.

Architecture Diagram:
```mermaid
{mermaid_content}
```

Parser-Generated Assessment:
{json.dumps(parser_truth, indent=2)}

Task: Enhance the following fields with concise, specific explanations (2-3 sentences max each):

1. For each attack path, provide a specific "rationale" explaining the vulnerability
2. For "description", provide a 1-sentence architecture summary
3. For overall "rationale", provide a 2-sentence security posture summary

Output ONLY valid JSON matching the original schema with enhanced fields.
"""

    try:
        if llm_model:
            response = generate_response_with_system(user_prompt, system_prompt, model=llm_model, max_tokens=2000)
        else:
            response = generate_response_with_system(user_prompt, system_prompt, max_tokens=2000)

        # Extract JSON from response
        response_text = response.strip()
        if "```json" in response_text:
            response_text = response_text.split("```json")[1].split("```")[0].strip()
        elif "```" in response_text:
            response_text = response_text.split("```")[1].split("```")[0].strip()

        enhanced = json.loads(response_text)
        enhanced["metadata"]["generated_by"] = "parser+llm"

        logger.info("LLM enhancement successful")
        return enhanced

    except Exception as e:
        logger.error(f"LLM enhancement failed: {e}")
        return parser_truth


def save_ground_truth(ground_truth: Dict, output_path: Optional[str] = None) -> str:
    """
    Save ground truth to JSON file.

    Args:
        ground_truth: Ground truth dict
        output_path: Optional custom output path (default: tests/data/ground_truth/<name>.json)

    Returns:
        Path to saved file
    """
    if output_path:
        save_path = Path(output_path)
    else:
        mmd_name = Path(ground_truth["architecture"]).stem
        save_path = Path("tests/data/ground_truth") / f"{mmd_name}.json"

    save_path.parent.mkdir(parents=True, exist_ok=True)

    with open(save_path, 'w') as f:
        json.dump(ground_truth, f, indent=2)

    logger.info(f"Ground truth saved to {save_path}")
    return str(save_path)


if __name__ == "__main__":
    # Quick test
    import sys

    if len(sys.argv) < 2:
        print("Usage: python3 -m chatbot.modules.ground_truth_generator <mmd_file> [--llm]")
        sys.exit(1)

    mmd_file = sys.argv[1]
    use_llm = "--llm" in sys.argv

    logging.basicConfig(level=logging.INFO)

    truth = generate_ground_truth(mmd_file, use_llm=use_llm)
    output_path = save_ground_truth(truth)

    print(f"\n✅ Ground truth generated: {output_path}")
    print(f"\nSummary:")
    print(f"  Controls: {len(truth['controls_present'])} present, {len(truth['controls_missing'])} missing")
    print(f"  Attack Paths: {len(truth['expected_attack_paths'])}")
    print(f"  Risk Score: {truth['expected_risk_score']}/100")
    print(f"  Defensibility: {truth['expected_defensibility']}/100")
