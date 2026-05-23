"""
Per-Node MITRE Technique Mapping

Phase 3B Enhancement: Drill into every node of every attack path.

Instead of assigning 2-5 techniques to the entire path, this module:
1. Assigns specific MITRE techniques to EACH node based on its role
2. Creates detailed hop-by-hop TTP mapping
3. Enables precise control placement at vulnerable nodes
4. Provides complete attack narrative for each path

Node Role Taxonomy:
- Entry Point: Initial access techniques (T1190, T1566, T1078)
- Traversal: Execution, lateral movement, privilege escalation
- Target: Collection, exfiltration, impact
- Intermediary: Persistence, defense evasion, credential access
"""

from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


# ============================================================================
# COMPREHENSIVE NODE TYPE → TECHNIQUE MAPPING
# ============================================================================

# Entry Point Techniques (Initial Access - TA0001)
ENTRY_TECHNIQUES = {
    "internet": {
        "default": ["T1190"],  # Exploit Public-Facing Application
        "with_vpn": ["T1133"],  # External Remote Services
        "high_app_vuln": ["T1190", "T1133"],
    },
    "user": {
        "default": ["T1566", "T1078"],  # Phishing, Valid Accounts
        "with_mfa": ["T1621"],  # Multi-Factor Authentication Request Generation
    },
    "mobile": {
        "default": ["T1566", "T1078"],  # Phishing (mobile), Valid Accounts
        "note": "T1566.002 (Spearphishing Link) and T1078 for compromised mobile credentials"
    },
    "partner": {
        "default": ["T1199", "T1078"],  # Trusted Relationship, Valid Accounts
    },
    "supply_chain": {
        "default": ["T1195"],  # Supply Chain Compromise
    },
}

# Traversal Techniques by Node Type
TRAVERSAL_TECHNIQUES = {
    # Web/API Layer (Execution - TA0002)
    "web": ["T1059", "T1203"],  # Command Injection, Exploitation for Client Execution
    "api": ["T1059", "T1212"],  # Command Injection, Exploitation for Credential Access
    "gateway": ["T1190"],  # May still be exploitable if poorly configured

    # Application Layer (Execution - TA0002)
    "server": ["T1059", "T1203"],  # Command and Scripting Interpreter, Exploitation
    "application": ["T1059", "T1106"],  # Command Injection, Native API
    "service": ["T1059"],  # Command Injection
    "app": ["T1059", "T1203"],

    # Data Layer (Credential Access - TA0006, Lateral Movement - TA0008)
    "cache": ["T1213", "T1552"],  # Data from Info Repos, Unsecured Credentials
    "queue": ["T1213"],  # Data from Information Repositories
    "message": ["T1213", "T1114"],  # Email Collection if messaging

    # Auth/Identity Layer (Credential Access - TA0006)
    "auth": ["T1110", "T1556"],  # Brute Force, Modify Authentication Process
    "identity": ["T1110", "T1078"],  # Brute Force, Valid Accounts
    "sso": ["T1556"],  # Modify Authentication Process

    # Network Layer (Lateral Movement - TA0008)
    "network": ["T1090"],  # Proxy
    "router": ["T1090", "T1557"],  # Proxy, Man-in-the-Middle
    "load balancer": ["T1090"],  # Proxy
    "vpn": ["T1133"],  # External Remote Services

    # Admin/Management (Privilege Escalation - TA0004)
    "admin": ["T1068", "T1078"],  # Exploitation for Privilege Escalation, Valid Accounts
    "management": ["T1078", "T1548"],  # Valid Accounts, Abuse Elevation Control

    # Storage/Backup (Collection - TA0009)
    "storage": ["T1213", "T1530"],  # Data Repos, Data from Cloud Storage
    "backup": ["T1005", "T1213"],  # Data from Local System, Data Repos
    "s3": ["T1530"],  # Data from Cloud Storage Object
    "bucket": ["T1530"],
}

# Target Techniques (Collection - TA0009, Exfiltration - TA0010, Impact - TA0040)
TARGET_TECHNIQUES = {
    "database": ["T1213", "T1005", "T1567"],  # Data Repos, Local System, Exfil to Cloud
    "db": ["T1213", "T1005"],
    "secret": ["T1552", "T1555"],  # Unsecured Credentials, Credentials from Password Stores
    "key": ["T1552"],
    "credentials": ["T1552", "T1555"],
    "pii": ["T1213", "T1005"],  # Sensitive data collection
    "payment": ["T1213", "T1005"],
    "model": ["T1213", "T1567"],  # AI model theft (Data Repos + Exfiltration)
    "training_data": ["T1213", "T1530"],
}

# Impact Techniques (TA0040) - Added when RAPIDS shows high threat
# These represent the "final blow" in attacks - data destruction, encryption, service disruption
IMPACT_TECHNIQUES = {
    "ransomware": ["T1486", "T1490"],  # Data Encrypted for Impact, Inhibit System Recovery
    "data_destruction": ["T1485", "T1490"],  # Data Destruction, Inhibit System Recovery
    "denial_of_service": ["T1498", "T1499"],  # Network/Endpoint DoS
    "defacement": ["T1491"],  # Defacement
}


# ============================================================================
# PER-NODE TTP MAPPING
# ============================================================================

def map_node_to_techniques(
    node_id: str,
    node_label: str,
    position: str,
    controls_present: List[str],
    rapids: Optional[Dict] = None
) -> List[str]:
    """
    Map a single node to MITRE techniques based on its role in the attack path.

    Args:
        node_id: Node identifier
        node_label: Human-readable node label (e.g., "Web Server", "Database")
        position: Node position in path ("entry", "traversal", "target")
        controls_present: Architecture-wide controls
        rapids: RAPIDS assessment for context-aware technique assignment

    Returns:
        List of MITRE technique IDs applicable to this specific node
    """
    techniques = []
    label_lower = node_label.lower()
    controls_lower = [c.lower() for c in controls_present]

    logger.debug(f"Mapping node '{node_label}' (position={position})")

    # ========================================================================
    # ENTRY POINT NODE
    # ========================================================================
    if position == "entry":
        # Internet-facing entry
        if any(kw in label_lower for kw in ["internet", "public", "external"]):
            # Check exploitability if RAPIDS available
            if rapids:
                app_vuln_risk = rapids.get("application_vulns", {}).get("risk", 0)
                threshold = _calculate_exploitability_threshold(controls_present)

                if app_vuln_risk >= threshold:
                    techniques.extend(ENTRY_TECHNIQUES["internet"]["high_app_vuln"])
                    logger.info(f"Entry {node_label}: T1190 assigned (app_vuln_risk={app_vuln_risk})")
                else:
                    techniques.append("T1133")  # VPN/Remote Services only
                    logger.info(f"Entry {node_label}: Well-defended, T1190 skipped")
            else:
                techniques.extend(ENTRY_TECHNIQUES["internet"]["default"])

        # User/Client entry (Phishing vector)
        elif any(kw in label_lower for kw in ["user", "client", "employee", "admin"]):
            if "mfa" in controls_lower:
                techniques.extend(ENTRY_TECHNIQUES["user"]["with_mfa"])
            else:
                techniques.extend(ENTRY_TECHNIQUES["user"]["default"])

        # Mobile entry
        elif "mobile" in label_lower:
            techniques.extend(ENTRY_TECHNIQUES["mobile"]["default"])

        # Partner/3rd party entry
        elif any(kw in label_lower for kw in ["partner", "vendor", "third"]):
            techniques.extend(ENTRY_TECHNIQUES["partner"]["default"])

        # Supply chain entry
        elif any(kw in label_lower for kw in ["supplier", "supply"]):
            techniques.extend(ENTRY_TECHNIQUES["supply_chain"]["default"])

    # ========================================================================
    # TRAVERSAL NODE
    # ========================================================================
    elif position == "traversal":
        # Check all traversal patterns
        for node_type, techs in TRAVERSAL_TECHNIQUES.items():
            if node_type in label_lower:
                techniques.extend(techs)
                logger.debug(f"Traversal {node_label}: Matched '{node_type}' → {techs}")
                break  # Match first pattern only

        # Generic fallback for unrecognized traversal nodes
        if not techniques:
            techniques.append("T1059")  # Command Injection (generic)
            logger.warning(f"Traversal {node_label}: No specific match, using generic T1059")

    # ========================================================================
    # TARGET NODE
    # ========================================================================
    elif position == "target":
        # Check all target patterns
        matched = False
        for target_type, techs in TARGET_TECHNIQUES.items():
            if target_type in label_lower:
                techniques.extend(techs)
                logger.debug(f"Target {node_label}: Matched '{target_type}' → {techs}")
                matched = True
                break

        # Generic fallback for unrecognized targets
        if not matched:
            techniques.append("T1213")  # Data from Information Repositories (generic)
            logger.warning(f"Target {node_label}: No specific match, using generic T1213")

        # ADD IMPACT TECHNIQUES based on RAPIDS threats
        # Targets are where attacks culminate - data gets encrypted, destroyed, or exfiltrated
        if rapids:
            # Ransomware: Data encryption + recovery inhibition (risk score ≥40)
            ransomware_risk = rapids.get("ransomware", {}).get("risk", 0)
            if isinstance(ransomware_risk, (int, float)) and ransomware_risk >= 40:
                techniques.extend(IMPACT_TECHNIQUES["ransomware"])
                logger.info(f"Target {node_label}: Added ransomware impact techniques (T1486, T1490) - risk={ransomware_risk}")
            elif ransomware_risk in ["HIGH", "MEDIUM"]:  # Support label format too
                techniques.extend(IMPACT_TECHNIQUES["ransomware"])
                logger.info(f"Target {node_label}: Added ransomware impact techniques (T1486, T1490)")

            # Insider threat / Data destruction (risk score ≥50)
            insider_risk = rapids.get("insider_threat", {}).get("risk", 0)
            if isinstance(insider_risk, (int, float)) and insider_risk >= 50:
                if "T1485" not in techniques:  # Avoid duplicates
                    techniques.append("T1485")  # Data Destruction
                    logger.info(f"Target {node_label}: Added data destruction technique (T1485) - risk={insider_risk}")
            elif insider_risk == "HIGH":  # Support label format too
                if "T1485" not in techniques:
                    techniques.append("T1485")
                    logger.info(f"Target {node_label}: Added data destruction technique (T1485)")

    # Deduplicate
    return list(dict.fromkeys(techniques))  # Preserves order


def map_path_to_per_node_techniques(
    path: List[str],
    nodes: Dict[str, Dict],
    controls_present: List[str],
    rapids: Optional[Dict] = None
) -> Dict[str, List[str]]:
    """
    Map each node in attack path to specific MITRE techniques.

    Returns:
        Dict mapping node_id → [technique_ids]

    Example:
        {
            "Internet": ["T1190"],
            "WAF": [],
            "WebServer": ["T1059", "T1203"],
            "AppServer": ["T1059"],
            "Database": ["T1213", "T1005"]
        }
    """
    per_node_techniques = {}

    if not path or len(path) < 2:
        return per_node_techniques

    for idx, node_id in enumerate(path):
        node_label = nodes[node_id].get("label", node_id)

        # Determine position
        if idx == 0:
            position = "entry"
        elif idx == len(path) - 1:
            position = "target"
        else:
            position = "traversal"

        # Map node to techniques
        techniques = map_node_to_techniques(
            node_id=node_id,
            node_label=node_label,
            position=position,
            controls_present=controls_present,
            rapids=rapids
        )

        per_node_techniques[node_id] = techniques

        logger.info(f"Node {node_label} ({position}): {len(techniques)} techniques → {techniques}")

    return per_node_techniques


def get_all_techniques_from_path(per_node_map: Dict[str, List[str]]) -> List[str]:
    """
    Get deduplicated list of all techniques across entire path.

    Args:
        per_node_map: Output from map_path_to_per_node_techniques()

    Returns:
        Deduplicated list of technique IDs
    """
    all_techniques = []
    for techniques in per_node_map.values():
        all_techniques.extend(techniques)

    return list(dict.fromkeys(all_techniques))  # Deduplicate, preserve order


def _calculate_exploitability_threshold(controls_present: List[str]) -> int:
    """Calculate exploitability threshold based on defensive controls."""
    controls_lower = [c.lower() for c in controls_present]

    if "patching" in controls_lower and "waf" in controls_lower:
        return 50  # Well-defended
    elif "waf" in controls_lower:
        return 60
    else:
        return 70  # Conservative (assume exploitable)


# ============================================================================
# BACKWARDS COMPATIBILITY
# ============================================================================

def map_path_to_techniques_legacy(
    path: List[str],
    nodes: Dict[str, Dict],
    controls_present: List[str],
    rapids: Optional[Dict] = None
) -> List[str]:
    """
    Legacy function signature - returns flat list of techniques.

    Uses new per-node mapping internally but returns aggregated list.
    Maintains backwards compatibility with existing code.
    """
    per_node_map = map_path_to_per_node_techniques(path, nodes, controls_present, rapids)
    return get_all_techniques_from_path(per_node_map)


# ============================================================================
# TECHNIQUE METADATA (for reporting)
# ============================================================================

def get_technique_tactic(technique_id: str) -> str:
    """Get MITRE tactic name for technique (simplified mapping)."""
    tactic_map = {
        "T1190": "Initial Access",
        "T1133": "Initial Access",
        "T1566": "Initial Access",
        "T1078": "Initial Access",
        "T1199": "Initial Access",
        "T1195": "Initial Access",
        "T1621": "Credential Access",
        "T1059": "Execution",
        "T1203": "Execution",
        "T1106": "Execution",
        "T1212": "Credential Access",
        "T1110": "Credential Access",
        "T1556": "Credential Access",
        "T1552": "Credential Access",
        "T1555": "Credential Access",
        "T1068": "Privilege Escalation",
        "T1548": "Privilege Escalation",
        "T1090": "Command and Control",
        "T1557": "Credential Access",
        "T1213": "Collection",
        "T1530": "Collection",
        "T1005": "Collection",
        "T1114": "Collection",
        "T1567": "Exfiltration",
    }
    return tactic_map.get(technique_id, "Unknown")


if __name__ == "__main__":
    # Test case
    import sys
    logging.basicConfig(level=logging.INFO)

    test_nodes = {
        "Internet": {"label": "Internet"},
        "WAF": {"label": "WAF"},
        "WebServer": {"label": "Web Server"},
        "AppServer": {"label": "Application Server"},
        "Database": {"label": "Database"}
    }

    test_path = ["Internet", "WAF", "WebServer", "AppServer", "Database"]
    test_controls = ["WAF", "Rate Limiting"]
    test_rapids = {"application_vulns": {"risk": 75}}

    print("="*80)
    print("PER-NODE TTP MAPPING TEST")
    print("="*80)
    print(f"\nPath: {' → '.join([test_nodes[n]['label'] for n in test_path])}")
    print(f"Controls: {test_controls}")
    print(f"App Vuln Risk: {test_rapids['application_vulns']['risk']}/100\n")

    per_node = map_path_to_per_node_techniques(test_path, test_nodes, test_controls, test_rapids)

    print("\nPER-NODE TECHNIQUE MAPPING:")
    print("-"*80)
    for node_id, techniques in per_node.items():
        label = test_nodes[node_id]["label"]
        if techniques:
            print(f"{label:20s} → {', '.join(techniques)}")
        else:
            print(f"{label:20s} → (no techniques - control node)")

    print("\n" + "="*80)
    print(f"Total unique techniques: {len(get_all_techniques_from_path(per_node))}")
    print(f"Techniques: {get_all_techniques_from_path(per_node)}")
    print("="*80)
