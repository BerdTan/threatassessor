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

from chatbot.modules.mitre import MitreHelper, get_mitre_helper

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
        # Valid if internet/public/partner entry OR if the path contains public-facing components
        has_internet_entry = any(kw in entry_label for kw in [
            "internet", "public", "external", "mobile", "user", "partner", "vendor",
            "client", "ddos", "cdn", "waf", "vpn", "source", "data", "sensor",
        ])
        has_internet_in_path = any(kw in path_str for kw in [
            "internet", "public", "external", "ddos", "cdn", "partner", "source",
        ])
        has_web_component = any(kw in path_str for kw in [
            "web", "api", "server", "gateway", "load balancer", "service", "proxy", "app",
            "cluster", "node", "processor", "engine",
        ])

        if (has_internet_entry or has_internet_in_path) and has_web_component:
            validations.append((True, 0.1, "Public-facing entry with exploitable web components"))
        elif has_internet_entry or has_internet_in_path:
            validations.append((True, 0.05, "Public entry present — exploitation applicable"))
        elif has_web_component:
            validations.append((True, 0.04, "Web component present — exploitation plausible"))
        else:
            validations.append((False, -0.1, "No clear public-facing entry point"))

    # T1078 - Valid Accounts
    elif technique_id == "T1078":
        has_auth_component = any(kw in path_str for kw in [
            "auth", "login", "user", "identity", "sso", "mfa", "vpn", "remote",
            "portal", "admin", "api", "gateway",
        ])
        has_credential_target = any(kw in target_label for kw in [
            "database", "db", "user", "account", "credential", "server", "service",
        ])
        if has_auth_component or has_credential_target:
            validations.append((True, 0.1, "Authentication/credential components present"))
        else:
            validations.append((False, -0.05, "No clear authentication context"))

    # T1213 - Data from Information Repositories
    elif technique_id == "T1213":
        target_node_id = path_nodes[-1].lower() if path_nodes else ""
        DATA_KW = [
            "database", "db", "storage", "data", "repository", "file", "cache", "log",
            "registry", "primary", "replica", "queue", "message", "record", "archive",
        ]
        has_data_target = (
            any(kw in target_label for kw in DATA_KW)
            or any(kw in target_node_id for kw in DATA_KW)
            or any(kw in path_str for kw in DATA_KW)
        )

        if has_data_target:
            validations.append((True, 0.1, "Data repository target confirmed"))
        else:
            validations.append((False, -0.1, "Target is not a data repository"))

    # T1059 - Command and Scripting Interpreter
    elif technique_id == "T1059":
        # Execution environments: classic + modern + data-pipeline nodes
        has_exec_component = any(kw in path_str for kw in [
            "server", "application", "exec", "lambda", "function", "worker",
            "api", "service", "app", "microservice", "backend", "runtime",
            "cluster", "node", "processor", "engine", "kafka", "spark", "source",
        ])

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
        # Proxy technique valid at network intermediaries AND at any compromised server/app
        has_intermediary = any(kw in path_str for kw in [
            "proxy", "gateway", "load balancer", "cdn", "router", "firewall",
            "server", "application", "app", "service",
        ])
        if has_intermediary:
            validations.append((True, 0.08, "Intermediary/service component detected — proxy pivot applicable"))
        else:
            validations.append((False, -0.05, "No proxy/intermediary component"))

    # T1005 - Data from Local System
    elif technique_id == "T1005":
        has_data_component = any(kw in path_str for kw in [
            "db", "database", "storage", "file", "cache", "log", "repository", "data",
            "primary", "replica", "queue", "server", "record",
        ])
        if has_data_component:
            validations.append((True, 0.05, "Data storage component present"))
        else:
            validations.append((False, 0.0, "No local data storage component detected"))

    # T1567 - Exfiltration Over Web Service
    elif technique_id == "T1567":
        # Valid when there is any internet/external connectivity; attackers use Dropbox/GitHub etc.
        has_web_out = any(kw in path_str for kw in [
            "api", "gateway", "internet", "external", "web", "cdn", "upload",
            "user", "client", "mobile", "public", "server", "application", "app",
        ])
        if has_web_out:
            validations.append((True, 0.05, "Outbound connectivity present — exfil to web service applicable"))
        else:
            validations.append((False, 0.0, "No clear outbound channel detected"))

    # T1048 - Exfiltration Over Alternative Protocol (DNS/ICMP/custom channel)
    elif technique_id == "T1048":
        has_outbound = any(kw in path_str for kw in [
            "server", "application", "app", "service", "gateway", "worker", "broker",
            "internet", "external", "public", "api", "web", "user", "client",
            "kafka", "spark", "stream", "ingestion",
        ])
        if has_outbound:
            validations.append((True, 0.05, "Internet-facing node present — alt-protocol exfil applicable"))
        else:
            validations.append((False, 0.0, "No internet-facing node found for alt-protocol exfil"))

    # T1486 - Data Encrypted for Impact (ransomware)
    elif technique_id == "T1486":
        DATA_KW2 = ["db", "database", "storage", "file", "backup", "cache", "data",
                    "primary", "replica", "queue", "server", "record"]
        has_data = any(kw in path_str for kw in DATA_KW2)
        if has_data:
            validations.append((True, 0.05, "Data storage present — ransomware applicable"))
        else:
            validations.append((False, 0.0, "No data storage found for ransomware impact"))

    # T1490 - Inhibit System Recovery
    elif technique_id == "T1490":
        has_recovery = any(kw in path_str for kw in [
            "backup", "recovery", "restore", "snapshot", "replication", "replica",
        ])
        has_data = any(kw in path_str for kw in [
            "db", "database", "storage", "data", "cache", "primary", "server",
        ])
        if has_recovery or has_data:
            validations.append((True, 0.05, "Recovery/data components present — inhibition applicable"))
        else:
            validations.append((False, 0.0, "No recovery or data components detected"))

    # T1485 - Data Destruction
    elif technique_id == "T1485":
        has_data = any(kw in path_str for kw in [
            "db", "database", "storage", "file", "cache", "data", "log",
            "primary", "replica", "queue", "record", "server",
        ])
        if has_data:
            validations.append((True, 0.05, "Data components present — destruction applicable"))
        else:
            validations.append((False, 0.0, "No data components found for destruction"))

    # T1203 - Exploitation for Client Execution
    elif technique_id == "T1203":
        # Valid if client-facing or browser-accessible component present
        has_client = any(kw in path_str for kw in [
            "user", "client", "browser", "mobile", "app", "frontend", "web",
        ])
        if has_client:
            validations.append((True, 0.05, "Client-facing component present"))
        else:
            validations.append((False, 0.0, "No client-facing component for client exploitation"))

    # T1212 - Exploitation for Credential Access
    elif technique_id == "T1212":
        # Broadened: API gateways and service endpoints are valid T1212 targets
        has_auth = any(kw in path_str for kw in [
            "auth", "login", "credential", "user", "identity", "sso", "mfa", "password",
            "access control", "api", "gateway", "service", "endpoint",
        ])
        if has_auth:
            validations.append((True, 0.05, "Authentication/API component present for credential exploitation"))
        else:
            validations.append((False, 0.0, "No authentication component found"))

    # T1071 - Application Layer Protocol (C2 over HTTP/HTTPS/DNS)
    elif technique_id == "T1071":
        has_network_path = any(kw in path_str for kw in [
            "internet", "external", "api", "gateway", "web", "server", "service",
            "application", "backend", "cloud", "function", "lambda",
        ])
        if has_network_path:
            validations.append((True, 0.06, "Network-accessible component present — C2 over app layer applicable"))
        else:
            validations.append((False, 0.0, "No network-accessible component for application layer C2"))

    # T1021 - Remote Services (lateral movement via RDP/SSH/SMB/WinRM)
    elif technique_id == "T1021":
        has_internal = any(kw in path_str for kw in [
            "server", "workstation", "host", "internal", "network", "service",
            "application", "vm", "instance", "backend",
        ])
        if has_internal:
            validations.append((True, 0.08, "Internal services present — lateral movement applicable"))
        else:
            validations.append((False, 0.0, "No internal service components for lateral movement"))

    # T1040 - Network Sniffing
    elif technique_id == "T1040":
        # Valid at network infra AND any compromised server/app/cluster that can sniff local traffic
        has_network = any(kw in path_str for kw in [
            "network", "router", "switch", "vpn", "firewall", "gateway", "load balancer",
            "proxy", "internet", "server", "application", "app", "service", "node",
            "cluster", "kafka", "spark", "stream", "pipeline", "ingestion", "worker",
        ])
        if has_network:
            validations.append((True, 0.06, "Network/service component present — sniffing applicable"))
        else:
            validations.append((False, 0.0, "No network infrastructure for sniffing"))

    # T1041 - Exfiltration Over C2 Channel
    elif technique_id == "T1041":
        has_target = any(kw in path_str for kw in [
            "database", "db", "storage", "data", "file", "secret", "credential",
            "primary", "replica", "queue", "cache", "server", "record",
        ])
        has_egress = any(kw in path_str for kw in [
            "internet", "external", "api", "gateway", "web", "service", "partner",
        ])
        if has_target:
            validations.append((True, 0.06, "Data target present — C2 exfiltration applicable"))
        elif has_egress:
            validations.append((True, 0.04, "Outbound channel present for C2 exfiltration"))
        else:
            validations.append((False, 0.0, "No data target or egress channel for C2 exfiltration"))

    # T1046 - Network Service Discovery
    elif technique_id == "T1046":
        has_network = any(kw in path_str for kw in [
            "network", "server", "service", "host", "internal", "backend", "application",
        ])
        if has_network:
            validations.append((True, 0.06, "Network services present — discovery scan applicable"))
        else:
            validations.append((False, 0.0, "No network services to discover"))

    # T1083 - File and Directory Discovery
    elif technique_id == "T1083":
        has_system = any(kw in path_str for kw in [
            "server", "application", "service", "host", "storage", "file", "system",
            "backend", "api",
        ])
        if has_system:
            validations.append((True, 0.06, "System components present — file discovery applicable"))
        else:
            validations.append((False, 0.0, "No system components for file discovery"))

    # T1110 - Brute Force
    elif technique_id == "T1110":
        has_auth_surface = any(kw in path_str for kw in [
            "auth", "login", "user", "identity", "sso", "mfa", "password", "account",
            "internet", "external", "api", "gateway", "vpn", "portal", "remote",
            "partner", "web", "service", "source", "cluster", "node", "data",
        ])
        if has_auth_surface:
            validations.append((True, 0.07, "Authentication/access surface present — brute force applicable"))
        else:
            validations.append((False, 0.0, "No authentication surface for brute force"))

    # T1133 - External Remote Services
    elif technique_id == "T1133":
        has_external = any(kw in path_str for kw in [
            "internet", "external", "vpn", "remote", "public", "user", "client",
            "mobile", "api", "gateway", "partner", "vendor", "ddos", "cdn",
            "source", "sensor", "device", "iot", "data",
        ])
        if has_external:
            validations.append((True, 0.07, "External entry point present — remote services applicable"))
        else:
            validations.append((False, -0.05, "No external entry for remote services"))

    # T1210 - Exploitation of Remote Services
    elif technique_id == "T1210":
        has_remote_service = any(kw in path_str for kw in [
            "server", "service", "application", "api", "backend", "internal", "host",
        ])
        if has_remote_service:
            validations.append((True, 0.06, "Remote services present — exploitation applicable"))
        else:
            validations.append((False, 0.0, "No remote services to exploit"))

    # T1498 - Network Denial of Service
    elif technique_id == "T1498":
        has_network_surface = any(kw in path_str for kw in [
            "internet", "external", "public", "gateway", "load balancer", "cdn",
            "api", "web", "network", "ddos", "proxy", "reverse", "partner",
            "cluster", "source", "node", "service", "server",
        ])
        if has_network_surface:
            validations.append((True, 0.06, "Public network surface present — network DoS applicable"))
        else:
            validations.append((False, 0.0, "No public network surface for network DoS"))

    # T1499 - Endpoint Denial of Service
    elif technique_id == "T1499":
        has_endpoint = any(kw in path_str for kw in [
            "server", "application", "service", "api", "web", "backend",
            "gateway", "internet", "external", "app", "portal", "proxy",
            "cluster", "node", "kafka", "spark", "warehouse", "lake", "bi",
        ])
        if has_endpoint:
            validations.append((True, 0.06, "Application endpoint present — endpoint DoS applicable"))
        else:
            validations.append((False, 0.0, "No application endpoint for DoS"))

    # T1530 - Data from Cloud Storage Object
    elif technique_id == "T1530":
        has_cloud_storage = any(kw in path_str for kw in [
            "cloud", "s3", "blob", "storage", "bucket", "gcs", "azure", "aws", "gcp",
            "object", "data lake", "warehouse",
        ])
        has_data_target = any(kw in path_str for kw in [
            "database", "db", "data", "repository", "primary", "replica", "queue",
        ])
        if has_cloud_storage:
            validations.append((True, 0.08, "Cloud storage component confirmed"))
        elif has_data_target:
            validations.append((True, 0.04, "Data target present — cloud storage access plausible"))
        else:
            validations.append((False, 0.0, "No cloud storage components detected"))

    # T1562 - Impair Defenses
    elif technique_id == "T1562":
        has_security_component = any(kw in path_str for kw in [
            "firewall", "waf", "siem", "monitor", "log", "audit", "detection",
            "edr", "gateway", "security",
        ])
        has_any_component = len(path_str.split("→")) >= 2
        if has_security_component:
            validations.append((True, 0.08, "Security controls present — impairment applicable"))
        elif has_any_component:
            validations.append((True, 0.04, "Multi-hop path — defense impairment plausible"))
        else:
            validations.append((False, 0.0, "No security components to impair"))

    # T1565 - Data Manipulation
    elif technique_id == "T1565":
        has_data = any(kw in path_str for kw in [
            "database", "db", "storage", "data", "file", "cache", "log", "record",
            "primary", "replica", "queue", "server", "message",
        ])
        if has_data:
            validations.append((True, 0.06, "Data components present — manipulation applicable"))
        else:
            validations.append((False, 0.0, "No data components for manipulation"))

    # T1041 - Exfiltration Over C2 Channel (override for complex paths)
    # Rule already defined above — if we get here via fallthrough, use path-wide check
    # T1068 - Exploitation for Privilege Escalation
    elif technique_id == "T1068":
        has_system = any(kw in path_str for kw in [
            "server", "application", "service", "host", "backend", "api",
            "admin", "portal", "management",
        ])
        if has_system:
            validations.append((True, 0.06, "System components present — privilege escalation applicable"))
        else:
            validations.append((False, 0.0, "No system components for privilege escalation"))

    # T1087 - Account Discovery
    elif technique_id == "T1087":
        has_identity = any(kw in path_str for kw in [
            "auth", "identity", "user", "account", "directory", "admin", "portal",
            "ldap", "sso", "management", "server", "application",
        ])
        if has_identity:
            validations.append((True, 0.06, "Identity/account components present — discovery applicable"))
        else:
            validations.append((False, 0.0, "No identity components for account discovery"))

    # T1070 - Indicator Removal (log/artefact clearing)
    elif technique_id == "T1070":
        has_logging = any(kw in path_str for kw in [
            "log", "monitor", "siem", "audit", "server", "application", "service",
            "monitoring", "admin",
        ])
        if has_logging:
            validations.append((True, 0.05, "Logging/monitoring components present — indicator removal applicable"))
        else:
            validations.append((False, 0.0, "No logging components for indicator removal"))

    # T1199 - Trusted Relationship (3rd party / partner access)
    elif technique_id == "T1199":
        has_third_party = any(kw in path_str for kw in [
            "partner", "vendor", "third", "supplier", "trusted", "external",
            "vpn", "gateway", "api",
        ])
        if has_third_party:
            validations.append((True, 0.07, "Third-party access path present — trusted relationship applicable"))
        else:
            validations.append((False, 0.0, "No third-party components for trusted relationship"))

    # T1570 - Lateral Tool Transfer
    elif technique_id == "T1570":
        has_multi_hop = len([n for n in path_nodes if n]) >= 3
        has_internal = any(kw in path_str for kw in [
            "server", "application", "internal", "network", "host", "backend",
        ])
        if has_multi_hop and has_internal:
            validations.append((True, 0.06, "Multi-hop internal path — lateral tool transfer applicable"))
        elif has_internal:
            validations.append((True, 0.04, "Internal components present — tool transfer plausible"))
        else:
            validations.append((False, 0.0, "No internal path for lateral tool transfer"))

    # T1552 - Unsecured Credentials
    elif technique_id == "T1552":
        has_cred_surface = any(kw in path_str for kw in [
            "server", "application", "service", "api", "backend", "config",
            "database", "cache", "storage", "secret", "key", "credential",
            "cluster", "kafka", "spark", "node", "pipeline", "warehouse", "lake",
        ])
        if has_cred_surface:
            validations.append((True, 0.07, "Application/data components present — credential exposure applicable"))
        else:
            validations.append((False, 0.0, "No application components for credential exposure"))

    # T1018 - Remote System Discovery
    elif technique_id == "T1018":
        has_network = any(kw in path_str for kw in [
            "network", "server", "internal", "host", "backend", "service", "application",
        ])
        if has_network:
            validations.append((True, 0.06, "Network environment present — system discovery applicable"))
        else:
            validations.append((False, 0.0, "No network environment for remote discovery"))

    # T1027 - Obfuscated Files or Information
    elif technique_id == "T1027":
        has_execution = any(kw in path_str for kw in [
            "server", "application", "service", "api", "backend", "web",
        ])
        if has_execution:
            validations.append((True, 0.05, "Execution environment present — obfuscation applicable"))
        else:
            validations.append((False, 0.0, "No execution environment for obfuscation"))

    # T1098 - Account Manipulation
    elif technique_id == "T1098":
        has_identity = any(kw in path_str for kw in [
            "auth", "identity", "user", "account", "sso", "directory", "admin",
            "management", "iam", "ldap", "server", "application", "panel", "console",
            "portal", "cloud", "function", "lambda",
            "bi", "warehouse", "dashboard", "analytics", "reporting",
        ])
        if has_identity:
            validations.append((True, 0.07, "Identity/service component present — account manipulation applicable"))
        else:
            validations.append((False, 0.0, "No identity components for account manipulation"))

    # T1136 - Create Account
    elif technique_id == "T1136":
        has_identity = any(kw in path_str for kw in [
            "auth", "identity", "user", "account", "sso", "directory", "admin",
            "management", "iam",
        ])
        if has_identity:
            validations.append((True, 0.06, "Identity management present — account creation applicable"))
        else:
            validations.append((False, 0.0, "No identity management for account creation"))

    # T1557 - Adversary-in-the-Middle
    elif technique_id == "T1557":
        has_network_path = any(kw in path_str for kw in [
            "network", "router", "gateway", "proxy", "load balancer", "vpn",
            "server", "api",
        ])
        if has_network_path:
            validations.append((True, 0.07, "Network path present — AiTM applicable"))
        else:
            validations.append((False, 0.0, "No network path for AiTM attack"))

    # T1548 - Abuse Elevation Control Mechanism
    elif technique_id == "T1548":
        has_priv = any(kw in path_str for kw in [
            "admin", "management", "server", "application", "service",
        ])
        if has_priv:
            validations.append((True, 0.05, "Privileged component present — elevation abuse applicable"))
        else:
            validations.append((False, 0.0, "No privileged components for elevation abuse"))

    # Default: Check if technique name/description has keywords from path
    else:
        path_keywords = set(path_str.split())
        tech_keywords = set((tech_name + " " + tech_desc).split())
        overlap = len(path_keywords & tech_keywords)

        if overlap >= 3:
            # PLAUSIBLE prefix signals to downstream consumers (TATB) that this is a
            # keyword-heuristic match, not structural evidence — should carry half weight.
            validations.append((True, 0.05, f"[PLAUSIBLE] Generic match ({overlap} keywords overlap)"))
        else:
            validations.append((False, 0.0, "[PLAUSIBLE] Generic technique, no specific validation"))

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
    mitre = get_mitre_helper()
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
