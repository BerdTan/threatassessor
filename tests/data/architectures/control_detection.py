#!/usr/bin/env python3
"""
Control Detection Module - Phase 3B

Identifies security controls present in architecture diagrams and maps them
to MITRE ATT&CK mitigations. Validates against ground truth labels.

Detects:
- Perimeter controls (WAF, firewall, DDoS protection, IDS/IPS)
- Authentication (MFA, SSO, identity providers)
- Endpoint protection (EDR, antivirus, host firewall)
- Network segmentation (VLANs, micro-segmentation, DMZ)
- Data protection (encryption, backup, DLP)
- Monitoring (SIEM, logging, audit logs)
- Application security (rate limiting, input validation, API gateway)
"""

from typing import Dict, List, Set, Tuple
import re


# Control detection keywords (ordered by specificity)
CONTROL_KEYWORDS = {
    # Perimeter Security
    "ddos protection": ["ddos", "ddos protection", "ddos mitigation", "cloudflare", "akamai"],
    "waf": ["waf", "web application firewall", "modsecurity", "cloudflare waf"],
    "firewall": ["firewall", "fw", "ngfw", "next-gen firewall", "palo alto", "fortinet", "security group"],
    "load balancer": ["load balancer", "alb", "elb", "nlb", "f5", "haproxy", "nginx lb"],
    "reverse proxy": ["reverse proxy", "nginx", "apache proxy", "envoy"],
    "ids/ips": ["ids", "ips", "intrusion detection", "intrusion prevention", "snort", "suricata"],
    "cdn": ["cdn", "cloudflare", "cloudfront", "akamai", "fastly"],

    # Authentication & Access
    "mfa": ["mfa", "2fa", "multi-factor", "two-factor", "totp", "fido2", "yubikey"],
    "sso": ["sso", "single sign-on", "saml", "oauth", "oidc", "okta", "auth0"],
    "iam": ["iam", "identity access management", "rbac", "role-based access"],
    "least privilege": ["least privilege", "zero trust", "just-in-time", "jit access"],
    "vpn": ["vpn", "virtual private network", "wireguard", "openvpn"],

    # Endpoint Protection
    "edr": ["edr", "endpoint detection", "crowdstrike", "sentinelone", "defender atp"],
    "antivirus": ["antivirus", "av", "anti-malware", "defender", "mcafee"],
    "host firewall": ["host firewall", "windows firewall", "iptables", "ufw"],

    # Network Segmentation
    "network segmentation": ["network segmentation", "vlan", "subnet", "micro-segmentation", "vpc", "virtual network", "private subnet", "public subnet"],
    "dmz": ["dmz", "demilitarized zone", "perimeter network"],
    "zero trust": ["zero trust", "zt", "never trust", "zta"],

    # Data Protection
    "encryption": ["encryption", "encrypted", "crypto"],
    "encryption at rest": ["encryption at rest", "encrypted storage", "disk encryption", "tde"],
    "encryption in transit": ["encryption in transit", "tls", "ssl", "https", "mtls"],
    "backup": ["backup", "snapshot", "replication", "disaster recovery", "dr"],
    "dlp": ["dlp", "data loss prevention", "data leakage prevention"],

    # Monitoring & Logging
    "siem": ["siem", "security information", "splunk", "elastic siem", "sentinel"],
    "logging": ["logging", "log aggregation", "cloudwatch", "stackdriver"],
    "audit log": ["audit log", "audit trail", "access log", "activity log"],
    "monitoring": ["monitoring", "prometheus", "grafana", "datadog", "new relic"],

    # Application Security
    "api gateway": ["api gateway", "kong", "apigee", "aws api gateway"],
    "rate limiting": ["rate limit", "throttling", "rate throttle", "api limit"],
    "input validation": ["input validation", "sanitization", "parameterized query"],
    "waf rules": ["waf rule", "owasp top 10", "sql injection block"],

    # Database Security
    "database replication": ["database replication", "db replication", "read replica", "master-slave", "replica", "standby", "secondary db"],
    "database encryption": ["database encryption", "encrypted database", "encrypted db"],

    # Infrastructure Components (often act as controls)
    "cache": ["cache", "redis", "memcached", "elasticache", "caching layer"],
    "message queue": ["message queue", "queue", "kafka", "rabbitmq", "sqs", "pubsub", "event bus"],

    # Container/Cloud Security
    "container scanning": ["container scan", "image scan", "vulnerability scan", "trivy", "clair"],
    "secrets management": ["secrets management", "vault", "secrets manager", "key vault"],
    "service mesh": ["service mesh", "istio", "linkerd", "consul"],

    # AI-Specific Controls
    "sandbox": ["sandbox", "code execution sandbox", "isolated environment", "code execution", "execution sandbox"],
    "prompt filtering": ["prompt filter", "prompt injection filter", "input filter"],
    "output filtering": ["output filter", "content filter", "pii detection"],
    "model access control": ["model access control", "api key rotation", "token limit"],
}


# Control → MITRE Mitigation mapping
CONTROL_TO_MITIGATIONS = {
    "waf": ["M1050"],  # Exploit Protection
    "firewall": ["M1037", "M1030"],  # Filter Network Traffic, Network Segmentation
    "mfa": ["M1032"],  # Multi-factor Authentication
    "edr": ["M1047"],  # Audit
    "backup": ["M1053"],  # Data Backup
    "encryption at rest": ["M1041"],  # Encrypt Sensitive Information
    "encryption in transit": ["M1041"],  # Encrypt Sensitive Information
    "network segmentation": ["M1030"],  # Network Segmentation
    "least privilege": ["M1026"],  # Privileged Account Management
    "iam": ["M1026", "M1018"],  # Privileged Account Management, User Account Management
    "siem": ["M1047"],  # Audit
    "ids/ips": ["M1031"],  # Network Intrusion Prevention
    "rate limiting": ["M1037"],  # Filter Network Traffic
    "input validation": ["M1050"],  # Exploit Protection
    "sandbox": ["M1048"],  # Application Isolation and Sandboxing
}


def normalize_label(label: str) -> str:
    """Normalize node/edge label for matching."""
    return label.lower().strip()


def detect_controls_in_text(text: str) -> Set[str]:
    """
    Detect security controls mentioned in text using keyword matching.

    Args:
        text: Text to search (node label, edge label, or combined)

    Returns:
        Set of detected control names
    """
    normalized = normalize_label(text)
    detected = set()

    # Negation patterns - if these appear before control keyword, don't count it
    # Allow spaces, dashes, or other separators between negation and keyword (or end of string)
    negation_pattern = r'(?:no|without|missing|lacking|absent)(?:[\s\-]+|$)'

    # Sort by keyword specificity (longer phrases first to avoid false positives)
    for control_name, keywords in sorted(CONTROL_KEYWORDS.items(), key=lambda x: -max(len(k) for k in x[1])):
        for keyword in keywords:
            # Use word boundaries for more precise matching
            # For multi-word keywords, check exact phrase
            if ' ' in keyword:
                pattern = r'\b' + re.escape(keyword) + r'\b'
            else:
                # For single words, be more strict - match as standalone word or with punctuation
                pattern = r'(?:^|[\s\-/\(\)\[\]])' + re.escape(keyword) + r'(?:$|[\s\-/\(\)\[\]])'

            match = re.search(pattern, normalized)
            if match:
                # Check if negation appears before the match
                # Look for negation within last 20 chars before match
                text_before_match = normalized[max(0, match.start()-20):match.start()]
                if re.search(negation_pattern, text_before_match):
                    # Negation found, skip this control
                    break

                detected.add(control_name)
                break  # Found match for this control, move to next

    return detected


def detect_controls_in_architecture(nodes: List[Dict], edges: List[Dict], subgraphs: List[Dict] = None) -> Dict[str, List[str]]:
    """
    Detect all security controls present in architecture.

    Args:
        nodes: List of node dicts with 'id' and 'label'
        edges: List of edge dicts with 'source', 'target', 'label'
        subgraphs: Optional list of subgraph dicts (for segmentation detection)

    Returns:
        Dict with:
        - controls_present: List of detected controls
        - controls_by_node: Dict mapping node_id to list of controls
        - control_evidence: Dict mapping control to list of node IDs where found
    """
    controls_present = set()
    controls_by_node = {}
    control_evidence = {}

    subgraphs = subgraphs or []

    # Check each node
    for node in nodes:
        node_id = node["id"]
        label = node.get("label", node_id)

        detected = detect_controls_in_text(label)

        if detected:
            controls_by_node[node_id] = sorted(detected)
            controls_present.update(detected)

            for control in detected:
                if control not in control_evidence:
                    control_evidence[control] = []
                control_evidence[control].append({"node_id": node_id, "label": label})

    # Check edge labels (some controls appear in connections)
    for edge in edges:
        label = edge.get("label", "")
        if label:
            detected = detect_controls_in_text(label)
            controls_present.update(detected)

            for control in detected:
                if control not in control_evidence:
                    control_evidence[control] = []
                control_evidence[control].append({
                    "edge": f"{edge['source']} → {edge['target']}",
                    "label": label
                })

    # Check subgraphs for segmentation indicators
    if subgraphs and len(subgraphs) >= 2:
        # Multiple subgraphs often indicate network segmentation
        segmentation_keywords = ["tier", "zone", "layer", "vpc", "subnet", "dmz", "segment"]

        has_segmentation_keywords = any(
            any(kw in subgraph.get("label", "").lower() for kw in segmentation_keywords)
            for subgraph in subgraphs
        )

        if has_segmentation_keywords:
            controls_present.add("network segmentation")
            if "network segmentation" not in control_evidence:
                control_evidence["network segmentation"] = []
            control_evidence["network segmentation"].append({
                "subgraphs": [sg.get("label", sg.get("id", "")) for sg in subgraphs],
                "rationale": f"{len(subgraphs)} subgraphs with segmentation keywords detected"
            })

    return {
        "controls_present": sorted(controls_present),
        "controls_by_node": controls_by_node,
        "control_evidence": control_evidence,
    }


def map_controls_to_mitigations(controls: List[str]) -> List[Dict[str, str]]:
    """
    Map detected controls to MITRE ATT&CK mitigations.

    Args:
        controls: List of control names

    Returns:
        List of mitigation dicts with mitigation_id and description
    """
    mitigations = []
    mitigation_set = set()

    for control in controls:
        mitigation_ids = CONTROL_TO_MITIGATIONS.get(control, [])
        for mitigation_id in mitigation_ids:
            if mitigation_id not in mitigation_set:
                mitigation_set.add(mitigation_id)
                mitigations.append({
                    "mitigation_id": mitigation_id,
                    "control": control,
                    "description": f"Implemented via {control}",
                })

    return mitigations


def identify_missing_controls(
    architecture_type: str,
    present_controls: List[str]
) -> List[Dict[str, str]]:
    """
    Identify critical missing controls based on architecture type.

    Args:
        architecture_type: Type of architecture (e.g., "web_app", "cloud", "ai_system")
        present_controls: List of controls already present

    Returns:
        List of missing control recommendations with priority
    """
    # Baseline controls every architecture should have
    baseline_controls = [
        ("firewall", "critical", "Network boundary protection"),
        ("logging", "high", "Security event visibility"),
        ("backup", "high", "Data recovery capability"),
        ("mfa", "high", "Account security"),
    ]

    # Architecture-specific recommendations
    architecture_specific = {
        "web_app": [
            ("waf", "critical", "Web application protection"),
            ("rate limiting", "high", "DoS prevention"),
            ("input validation", "high", "Injection attack prevention"),
        ],
        "cloud": [
            ("iam", "critical", "Cloud access management"),
            ("encryption at rest", "high", "Data protection"),
            ("network segmentation", "high", "Lateral movement prevention"),
        ],
        "ai_system": [
            ("prompt filtering", "critical", "Prompt injection prevention"),
            ("rate limiting", "critical", "API abuse prevention"),
            ("sandbox", "high", "Code execution isolation"),
        ],
    }

    # Combine baseline + specific
    all_recommended = baseline_controls + architecture_specific.get(architecture_type, [])

    # Filter to only missing controls
    present_set = set(present_controls)
    missing = []

    for control, priority, rationale in all_recommended:
        if control not in present_set:
            missing.append({
                "control": control,
                "priority": priority,
                "rationale": rationale,
            })

    return missing


def calculate_control_coverage(present_controls: List[str], architecture_type: str) -> float:
    """
    Calculate control coverage score (0.0-1.0).

    Args:
        present_controls: List of controls detected
        architecture_type: Architecture type for baseline

    Returns:
        Coverage score (0.0 = no controls, 1.0 = all recommended controls)
    """
    missing = identify_missing_controls(architecture_type, present_controls)
    baseline_count = 4  # 4 baseline controls

    # Architecture-specific control counts
    specific_counts = {
        "web_app": 3,
        "cloud": 3,
        "ai_system": 3,
    }

    total_recommended = baseline_count + specific_counts.get(architecture_type, 0)
    missing_count = len(missing)
    present_count = total_recommended - missing_count

    return max(0.0, min(1.0, present_count / total_recommended))


if __name__ == "__main__":
    # Quick test
    test_nodes = [
        {"id": "WAF", "label": "Web Application Firewall"},
        {"id": "LB", "label": "Load Balancer"},
        {"id": "MFA", "label": "Multi-Factor Auth"},
        {"id": "DB", "label": "Database"},
    ]

    result = detect_controls_in_architecture(test_nodes, [])
    print(f"Detected controls: {result['controls_present']}")
    print(f"Coverage: {calculate_control_coverage(result['controls_present'], 'web_app'):.1%}")
