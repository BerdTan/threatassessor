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
# Each entry maps a keyword to techniques across multiple tactics:
# Execution (TA0002), Persistence (TA0003), Privilege Escalation (TA0004),
# Defense Evasion (TA0005), Credential Access (TA0006), Discovery (TA0007),
# Lateral Movement (TA0008), Collection (TA0009), C2 (TA0011), Exfiltration (TA0010)
TRAVERSAL_TECHNIQUES = {
    # Web/API Layer
    # T1027/T1018 tightened — removed from web/api (too noisy, 53% FP); kept at server/app
    # T1212 kept at api (credential exploitation — valid for API auth endpoints)
    "web":         ["T1059", "T1083", "T1071", "T1078"],
    "api":         ["T1059", "T1212", "T1083", "T1071", "T1078"],
    # T1090 (Proxy): attacker uses gateway as proxy pivot after compromise
    # T1087/T1040/T1557 added: discovery + sniffing + AiTM via compromised gateway
    "gateway":     ["T1190", "T1071", "T1078", "T1562", "T1090", "T1087", "T1040", "T1557"],

    # Application Layer
    # T1570 (lateral tool transfer) re-added: valid at any multi-hop server pivot
    # T1087 (account discovery) added: post-compromise enumeration on server/app nodes
    # T1040 (network sniffing) added: passive sniffing after server/app compromise
    # T1557 (AiTM) added: compromised server can intercept traffic
    # T1098 (Account Manipulation) added: post-exploitation persistence
    # T1212 (Exploit Credential Access) added: credential exploitation at service level
    # T1090 (Proxy) added: compromised server/app commonly used as proxy pivot
    "server":      ["T1059", "T1083", "T1046", "T1021", "T1210", "T1071",
                    "T1078", "T1552", "T1557", "T1018", "T1027", "T1562",
                    "T1098", "T1212", "T1090", "T1087", "T1040", "T1570"],
    "application": ["T1059", "T1083", "T1046", "T1210", "T1071",
                    "T1078", "T1552", "T1027", "T1562", "T1098", "T1212",
                    "T1090", "T1087", "T1040", "T1570"],
    "service":     ["T1059", "T1046", "T1210", "T1071", "T1078", "T1562",
                    "T1212", "T1087", "T1040", "T1557"],
    "app":         ["T1059", "T1083", "T1210", "T1071", "T1078", "T1212",
                    "T1087", "T1040", "T1557"],

    # Data Layer
    "cache":       ["T1213", "T1552"],
    "queue":       ["T1213"],
    "message":     ["T1213", "T1114", "T1071"],

    # Auth/Identity Layer — T1098/T1136 kept ONLY here (auth-specific nodes)
    "auth":        ["T1110", "T1556", "T1078", "T1021", "T1098", "T1136", "T1212"],
    "identity":    ["T1110", "T1078", "T1021", "T1098", "T1136", "T1212"],
    "sso":         ["T1556", "T1078", "T1098", "T1212"],

    # Network Layer — T1090 (Proxy) added throughout; firewall gets T1090 (evasion via proxy)
    # T1570 removed from network (lateral tool transfer not applicable at network infra)
    "network":     ["T1090", "T1021", "T1040", "T1046", "T1078", "T1018"],
    "router":      ["T1090", "T1557", "T1040", "T1046", "T1078", "T1018", "T1562"],
    "load balancer": ["T1090", "T1562"],
    "cdn":         ["T1090", "T1071", "T1562"],
    "vpn":         ["T1133", "T1021", "T1040", "T1078", "T1562"],
    "firewall":    ["T1562", "T1040", "T1090"],
    "proxy":       ["T1090", "T1071", "T1562"],

    # Admin/Management — T1087 (Account Discovery) kept here
    # T1098/T1136 kept ONLY at admin/management (100% FP elsewhere)
    "admin":       ["T1068", "T1078", "T1021", "T1083", "T1098", "T1136", "T1087"],
    "management":  ["T1078", "T1548", "T1021", "T1083", "T1098", "T1136", "T1087"],
    # Directory / Identity services — explicit T1087 here
    "directory":   ["T1087", "T1078", "T1110", "T1098", "T1136", "T1040"],
    "ldap":        ["T1087", "T1078", "T1110", "T1040"],
    "active directory": ["T1087", "T1078", "T1110", "T1098", "T1136", "T1040"],
    "domain":      ["T1087", "T1078", "T1098", "T1136"],

    # Storage/Backup
    "storage":     ["T1213", "T1530", "T1083"],
    "backup":      ["T1005", "T1213", "T1083"],
    "s3":          ["T1530", "T1083"],
    "bucket":      ["T1530", "T1083"],

    # Monitoring/Logging (Defense Evasion target)
    "monitor":     ["T1562", "T1070"],
    "log":         ["T1562", "T1070"],
    "siem":        ["T1562", "T1070"],

    # Microservice/Container
    "container":   ["T1610", "T1059", "T1083"],
    "pod":         ["T1610", "T1059"],
    "kubernetes":  ["T1610", "T1613", "T1046"],
    "docker":      ["T1610", "T1059"],

    # CI/CD
    "pipeline":    ["T1195", "T1059", "T1552"],
    "ci":          ["T1195", "T1552"],
    "cd":          ["T1195", "T1059"],
    "jenkins":     ["T1195", "T1059"],

    # AI / Agentic System nodes — MITRE ATT&CK + MITRE ATLAS (AML.T*) techniques
    # ATLAS techniques are injected alongside ATT&CK so both frameworks inform the path.
    # prompt: prompt injection (direct AML.T0051.000) → code exec + process injection
    "prompt":      ["T1059", "T1055", "T1203", "T1565", "T1213",
                    "AML.T0051", "AML.T0051.000"],
    # orchestrat: hub node — full model access + inference API abuse + lateral movement
    "orchestrat":  ["T1059", "T1055", "T1021", "T1552", "T1213", "T1087", "T1040",
                    "AML.T0051", "AML.T0054", "AML.T0044", "AML.T0040", "AML.T0024"],
    # tool registry: maps to tools — jailbreak to reach tools + model inference abuse
    "tool registry": ["T1059", "T1548", "T1552", "T1528", "T1087",
                      "AML.T0044", "AML.T0040"],
    "tool reg":    ["T1059", "T1548", "T1552", "T1528", "T1087",
                    "AML.T0044", "AML.T0040"],
    # llm / LLM gateway: prompt injection + jailbreak + inference API abuse + resource abuse
    "llm":         ["T1552", "T1528", "T1496", "T1071", "T1041", "T1573",
                    "AML.T0051", "AML.T0051.000", "AML.T0051.001",
                    "AML.T0054", "AML.T0048", "AML.T0040", "AML.T0024", "AML.T0025"],
    # vector db / embedding: training data poisoning + indirect prompt injection + exfil
    "vector":      ["T1565", "T1213", "T1041", "T1530",
                    "AML.T0020", "AML.T0018", "AML.T0051.001", "AML.T0025"],
    "embedding":   ["T1565", "T1213", "T1552", "T1041",
                    "AML.T0020", "AML.T0051.001", "AML.T0025"],
    # document store: indirect prompt injection via ingested docs + data poisoning + exfil
    "document":    ["T1213", "T1530", "T1041", "T1565", "T1119",
                    "AML.T0051.001", "AML.T0020", "AML.T0025"],
    # web search tool: indirect prompt injection via search results + SSRF + session hijack
    "web search":  ["T1090", "T1185", "T1071", "T1217",
                    "AML.T0051.001"],
    "websearch":   ["T1090", "T1185", "T1071", "T1217",
                    "AML.T0051.001"],
    # code execution sandbox: jailbreak to reach sandbox + sandbox escape + external harms
    "code exec":   ["T1059", "T1548", "T1068", "T1203", "T1055",
                    "AML.T0051.001", "AML.T0054", "AML.T0048"],
    "codeexec":    ["T1059", "T1548", "T1068", "T1203", "T1055",
                    "AML.T0051.001", "AML.T0054", "AML.T0048"],
    "sandbox":     ["T1059", "T1548", "T1068", "T1055",
                    "AML.T0054", "AML.T0048"],
    # session store: session hijacking + credential access
    "session":     ["T1185", "T1552", "T1056", "T1078"],
    # audit log: defense evasion (clearing logs) + indicator removal
    "audit":       ["T1562", "T1070", "T1489"],
    "auditlog":    ["T1562", "T1070", "T1489"],
    # api integrations / external APIs: inference API abuse + exfil + C2 + credential theft
    "api integrat": ["T1090", "T1071", "T1528", "T1041", "T1573",
                     "AML.T0040", "AML.T0025"],
    "external api": ["T1090", "T1071", "T1528", "T1041",
                     "AML.T0040", "AML.T0025"],

    # Data Pipeline / Streaming / Analytics
    # These nodes are data-in-motion (Kafka/Spark) or analytics endpoints (BI/ML)
    "kafka":       ["T1040", "T1565", "T1059", "T1213"],  # sniff stream + inject + query
    "spark":       ["T1059", "T1213", "T1565", "T1552"],  # code execution + data access
    "stream":      ["T1040", "T1565", "T1213"],
    "ingestion":   ["T1190", "T1565", "T1059"],           # entry to pipeline — exploit + inject
    "broker":      ["T1040", "T1565", "T1071"],           # message broker C2 channel
    "worker":      ["T1059", "T1210", "T1021"],
    "processor":   ["T1059", "T1210", "T1565"],
    "analytics":   ["T1213", "T1041", "T1565"],
    "bi":          ["T1213", "T1041", "T1565"],           # BI dashboard — data exfil target
    "reporting":   ["T1213", "T1041"],
    "etl":         ["T1565", "T1059", "T1213"],           # data manipulation in transform
    "warehouse":   ["T1213", "T1530", "T1041", "T1565"],  # data warehouse — collection + exfil
    "data lake":   ["T1213", "T1530", "T1041", "T1565"],
    "datalake":    ["T1213", "T1530", "T1041", "T1565"],

    # Cloud-specific
    "lambda":      ["T1648", "T1059", "T1530"],
    "function":    ["T1648", "T1059", "T1530"],
    "cloud":       ["T1530", "T1071", "T1578"],
    "blob":        ["T1530", "T1041"],
    "gcs":         ["T1530", "T1041"],
    "gcp":         ["T1530", "T1071"],
    "azure":       ["T1530", "T1071", "T1578"],
    "aws":         ["T1530", "T1071"],
    "rds":         ["T1213", "T1530", "T1041"],
    "cosmos":      ["T1213", "T1530", "T1041"],
    "dynamo":      ["T1213", "T1530", "T1041"],
    "bigquery":    ["T1213", "T1530", "T1041"],
    "redshift":    ["T1213", "T1530", "T1041"],
    "object store": ["T1530", "T1041"],
}

# Target Techniques (Collection - TA0009, Exfiltration - TA0010, Impact - TA0040)
# NOTE: All matches are applied (no break) — a node may match multiple keywords.
TARGET_TECHNIQUES = {
    "database": ["T1213", "T1005", "T1041", "T1530", "T1565"],
    "db":       ["T1213", "T1005", "T1041", "T1565"],
    "secret":   ["T1552", "T1555", "T1041"],
    "key":      ["T1552", "T1041"],
    "credentials": ["T1552", "T1555", "T1041"],
    "pii":      ["T1213", "T1005", "T1041", "T1530", "T1565"],
    "payment":  ["T1213", "T1005", "T1041", "T1530", "T1565"],
    "model":    ["T1213", "T1041", "T1530", "T1567"],
    "training_data": ["T1213", "T1530", "T1041", "T1565"],
    "file":     ["T1005", "T1083", "T1041", "T1565"],
    "share":    ["T1039", "T1041", "T1565"],
    "repo":     ["T1213", "T1041", "T1530"],
    "vault":    ["T1552", "T1555", "T1041"],
    "storage":  ["T1530", "T1213", "T1041", "T1565"],
    "bucket":   ["T1530", "T1041"],
    "object":   ["T1530", "T1041"],
    "blob":     ["T1530", "T1041"],
    "data":     ["T1213", "T1530", "T1041", "T1565"],
    "lake":     ["T1213", "T1530", "T1041"],
    "warehouse": ["T1213", "T1530", "T1041"],
    # Admin panel as target: account takeover + privilege escalation persist
    "admin":    ["T1098", "T1078", "T1213", "T1041"],
    "panel":    ["T1098", "T1078", "T1213"],
    "dashboard": ["T1213", "T1041", "T1098"],
    "portal":   ["T1098", "T1078", "T1213"],
    "console":  ["T1098", "T1078", "T1548"],
    "rds":      ["T1213", "T1530", "T1041"],
    "cosmos":   ["T1213", "T1530", "T1041"],
    "dynamo":   ["T1213", "T1530", "T1041"],
    "bigquery": ["T1213", "T1530", "T1041"],
    "gcs":      ["T1530", "T1041"],
    "cloud storage": ["T1530", "T1041"],
    "object store":  ["T1530", "T1041"],
}

# Impact Techniques (TA0040) - Added when RAPIDS shows high threat
# These represent the "final blow" in attacks - data destruction, encryption, service disruption
IMPACT_TECHNIQUES = {
    "ransomware":        ["T1486", "T1490"],         # Data Encrypted for Impact, Inhibit Recovery
    "data_destruction":  ["T1485", "T1490", "T1565"], # Destruction + Manipulation
    "denial_of_service": ["T1498", "T1499"],          # Network DoS, Endpoint DoS
    "defacement":        ["T1491"],                   # Defacement
    "data_manipulation": ["T1565"],                   # Data Manipulation
}


# ============================================================================
# PER-NODE TTP MAPPING
# ============================================================================

def map_node_to_techniques(
    node_id: str,
    node_label: str,
    position: str,
    controls_present: List[str],
    rapids: Optional[Dict] = None,
    has_backup: bool = False,
    has_cloud: bool = False,
    has_internet: bool = False,
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
            # Applicability: T1190 + T1133 always present (topology baseline)
            techniques.extend(["T1190", "T1133", "T1110"])  # + Brute Force always applicable
            logger.info(f"Entry {node_label}: T1190+T1133+T1110 assigned (applicability baseline)")

        # Internal application / service pivot entry — attacker is already past initial
        # access. T1133 (External Remote Services) is a network-boundary technique and
        # does not apply to internal compute, serverless, or app-layer nodes.
        # Must precede the "admin" / "user" branch to avoid "admin console" being
        # misclassified as a human entry point.
        elif any(kw in label_lower for kw in [
            # Web / app tier
            "web app", "webapp", "web server", "webserver", "web ui", "webui",
            "app server", "appserver", "api server", "api gateway", "api endpoint",
            "portal", "admin console", "admin portal",
            # Serverless / FaaS
            "lambda", "cloud function", "serverless", "function app", "azure function",
            # Container / PaaS
            "container app", "container service", "app service",
            # Auth / identity
            "auth server", "auth service", "identity provider", "idp", "oauth",
        ]):
            techniques.extend(["T1190", "T1059", "T1083", "T1210", "T1078", "T1110"])
            logger.info(f"Entry {node_label}: Internal app/service pivot entry — T1133 excluded (not a network boundary)")

        # User/Client/Visitor entry — phishing + credential abuse + external remote access
        elif any(kw in label_lower for kw in [
            "user", "client", "employee", "admin", "visitor", "browser",
            "end user", "end-user", "citizen", "staff", "gov", "tenant",
            "customer", "person", "operator",
        ]):
            if "mfa" in controls_lower:
                techniques.extend(ENTRY_TECHNIQUES["user"]["with_mfa"])
            else:
                techniques.extend(ENTRY_TECHNIQUES["user"]["default"])
            # External remote access and brute force always applicable for human entry points
            techniques.extend(["T1110", "T1133"])

        # Mobile entry
        elif "mobile" in label_lower:
            techniques.extend(ENTRY_TECHNIQUES["mobile"]["default"])
            techniques.extend(["T1110", "T1133"])

        # Partner/3rd party entry
        elif any(kw in label_lower for kw in ["partner", "vendor", "third"]):
            techniques.extend(ENTRY_TECHNIQUES["partner"]["default"])
            techniques.append("T1133")

        # Supply chain entry
        elif any(kw in label_lower for kw in ["supplier", "supply"]):
            techniques.extend(ENTRY_TECHNIQUES["supply_chain"]["default"])

        # Generic external entry fallback (any unrecognised entry node — applicability baseline)
        if not techniques:
            techniques.extend(["T1190", "T1133", "T1110"])
            logger.info(f"Entry {node_label}: Generic external entry fallback")

    # ========================================================================
    # TRAVERSAL NODE
    # ========================================================================
    elif position == "traversal":
        # Match ALL applicable patterns — a node may match multiple types
        # (e.g. "App Server" matches both "app" and "server")
        for node_type, techs in TRAVERSAL_TECHNIQUES.items():
            if node_type in label_lower:
                techniques.extend(techs)
                logger.debug(f"Traversal {node_label}: Matched '{node_type}' → {techs}")

        # Generic fallback for unrecognized traversal nodes
        if not techniques:
            techniques.extend(["T1059", "T1083"])  # Execution + Discovery (generic)
            logger.warning(f"Traversal {node_label}: No specific match, using generic fallback")

        # T1048 (Exfil over Alt Protocol) — DNS/ICMP/custom channel exfil; applicable at any
        # internet-facing traversal node where an attacker has code execution
        if has_internet and any(kw in label_lower for kw in [
            "server", "application", "app", "service", "gateway", "worker", "broker",
        ]) and "T1048" not in techniques:
            techniques.append("T1048")

    # ========================================================================
    # TARGET NODE
    # ========================================================================
    elif position == "target":
        # Match ALL applicable patterns — targets often match multiple keywords
        for target_type, techs in TARGET_TECHNIQUES.items():
            if target_type in label_lower:
                techniques.extend(techs)
                logger.debug(f"Target {node_label}: Matched '{target_type}' → {techs}")

        # Generic fallback for unrecognized targets — split by node role
        if not techniques:
            is_network_node = any(kw in label_lower for kw in [
                "cdn", "edge", "cache", "proxy", "load balancer", "firewall",
                "router", "switch", "gateway", "waf", "dns", "ingress",
            ])
            if is_network_node:
                # Network edge targets: availability + config manipulation — NOT data theft
                techniques.extend(["T1562", "T1071", "T1090"])
                logger.warning(f"Target {node_label}: Network edge fallback (T1562/T1071/T1090)")
            else:
                # Unknown data-bearing targets: default data access + exfil
                techniques.extend(["T1213", "T1530", "T1041"])
                logger.warning(f"Target {node_label}: Data target fallback (T1213/T1530/T1041)")

        # T1567 (Exfil Over Web Service) — applicable when arch has internet access or cloud nodes
        # Attackers use Dropbox/GitHub/S3 as exfil channels regardless of whether the arch uses cloud
        if (has_cloud or has_internet) and "T1567" not in techniques:
            techniques.append("T1567")

        # ADD IMPACT TECHNIQUES
        # Applicability baseline — DoS always applicable to any internet-accessible service
        techniques.extend(IMPACT_TECHNIQUES["denial_of_service"])   # T1498, T1499
        techniques.append("T1565")                                    # Data Manipulation

        if rapids:
            # Ransomware: T1486 (encrypt) fires at ≥40
            # T1490 (inhibit recovery) only fires when arch has explicit backup/recovery nodes
            # — destructive campaigns target recovery mechanisms, not generic webapps
            ransomware_risk = rapids.get("ransomware", {}).get("risk", 0)
            if isinstance(ransomware_risk, (int, float)) and ransomware_risk >= 40:
                techniques.append("T1486")  # Data Encrypted for Impact
                if has_backup and ransomware_risk >= 70:
                    techniques.append("T1490")  # Inhibit Recovery: backup infra + high risk only
                logger.info(f"Target {node_label}: ransomware risk={ransomware_risk} has_backup={has_backup}")
            elif ransomware_risk in ["HIGH", "MEDIUM"]:
                techniques.append("T1486")

            # Insider threat / Data destruction + manipulation (risk score ≥50)
            insider_risk = rapids.get("insider_threat", {}).get("risk", 0)
            if isinstance(insider_risk, (int, float)) and insider_risk >= 50:
                for t in ["T1485", "T1565"]:  # Data Destruction + Data Manipulation
                    if t not in techniques:
                        techniques.append(t)
                logger.info(f"Target {node_label}: Added destruction/manipulation techniques - risk={insider_risk}")
            elif insider_risk == "HIGH":
                for t in ["T1485", "T1565"]:
                    if t not in techniques:
                        techniques.append(t)

            # Supply chain / integrity attacks — data manipulation risk
            supply_risk = rapids.get("supply_chain", {}).get("risk", 0)
            if isinstance(supply_risk, (int, float)) and supply_risk >= 50:
                if "T1565" not in techniques:
                    techniques.append("T1565")  # Data Manipulation

    # Deduplicate
    return list(dict.fromkeys(techniques))  # Preserves order


def build_technique_context(
    per_node_techniques: Dict[str, List[str]],
    path: List[str],
    nodes: Dict[str, Dict],
    controls_present: List[str],
    rapids: Optional[Dict] = None,
) -> Dict[str, Dict]:
    """
    Build technique_context — annotates every technique with its dimension:
      - applicability: topology-driven baseline (always present, drives recall)
      - exploitability: RAPIDS-confirmed depth (drives AP criticality)

    Returns:
        { "T1190": {"dimension": "exploitability", "node": "Internet",
                    "rapids_signal": "application_vulns", "risk_score": 75},
          "T1059": {"dimension": "applicability", "node": "WebApp"}, ... }
    """
    context = {}

    # All topology-derived techniques start as applicability
    for node_id, techs in per_node_techniques.items():
        node_label = nodes.get(node_id, {}).get("label", node_id)
        for t in techs:
            if t not in context:
                context[t] = {"dimension": "applicability", "node": node_label}

    if not rapids:
        return context

    # Upgrade to exploitability where RAPIDS confirms it
    controls_lower = [c.lower() for c in controls_present]

    # Internet-facing entry — exploitability if app_vuln_risk exceeds threshold
    if path:
        entry_label = nodes.get(path[0], {}).get("label", "").lower()
        if any(kw in entry_label for kw in ["internet", "public", "external"]):
            app_vuln_risk = rapids.get("application_vulns", {}).get("risk", 0)
            threshold = _calculate_exploitability_threshold(controls_present)
            if isinstance(app_vuln_risk, (int, float)) and app_vuln_risk >= threshold:
                context["T1190"] = {
                    "dimension": "exploitability",
                    "node": nodes.get(path[0], {}).get("label", path[0]),
                    "rapids_signal": "application_vulns",
                    "risk_score": app_vuln_risk,
                    "threshold": threshold,
                }
                logger.info(f"T1190 upgraded to exploitability: risk={app_vuln_risk} >= threshold={threshold}")

    # Impact techniques — exploitability when RAPIDS risk exceeds threshold
    RAPIDS_IMPACT_MAP = [
        ("ransomware",     40, ["T1486", "T1490"]),
        ("dos",            35, ["T1498", "T1499"]),
        ("insider_threat", 50, ["T1485", "T1565"]),
        ("supply_chain",   50, ["T1565"]),
    ]
    for signal, threshold, techs in RAPIDS_IMPACT_MAP:
        risk = rapids.get(signal, {}).get("risk", 0)
        if isinstance(risk, (int, float)) and risk >= threshold:
            for t in techs:
                if t in context:
                    context[t] = {
                        "dimension": "exploitability",
                        "node": nodes.get(path[-1] if path else "", {}).get("label", "target"),
                        "rapids_signal": signal,
                        "risk_score": risk,
                    }

    return context


def _arch_has_cloud_nodes(nodes: Dict[str, Dict]) -> bool:
    """Return True if any node label suggests cloud infrastructure."""
    kw = ["cloud", "aws", "azure", "gcp", "s3", "blob", "gcs", "lambda", "function",
          "rds", "dynamo", "cosmos", "redshift", "bigquery", "cloud storage", "object store"]
    return any(
        any(k in n.get("label", "").lower() for k in kw)
        for n in nodes.values()
    )


def _arch_has_backup_nodes(nodes: Dict[str, Dict]) -> bool:
    """Return True if any node label suggests explicit backup/recovery/snapshot infrastructure."""
    kw = ["backup", "recovery", "snapshot", "archive", "replica", "replication",
          "disaster", "dr ", "cold store", "warm standby"]
    return any(
        any(k in n.get("label", "").lower() for k in kw)
        for n in nodes.values()
    )


def _arch_has_internet_nodes(nodes: Dict[str, Dict]) -> bool:
    """Return True if any node label suggests an internet-facing entry point."""
    kw = ["internet", "public", "external", "user", "client", "mobile", "browser"]
    return any(
        any(k in n.get("label", "").lower() for k in kw)
        for n in nodes.values()
    )


def _arch_has_perimeter_nodes(nodes: Dict[str, Dict]) -> bool:
    """Return True if the arch has any perimeter/filtering node (firewall, WAF, gateway, IDS)."""
    kw = ["firewall", "waf", "gateway", "ids", "ips", "proxy", "router", "dmz",
          "load balancer", "cdn", "perimeter", "edge", "ngfw"]
    return any(
        any(k in n.get("label", "").lower() for k in kw)
        for n in nodes.values()
    )


def _arch_has_auth_nodes(nodes: Dict[str, Dict]) -> bool:
    """Return True if the arch has a dedicated auth/identity node."""
    kw = ["auth", "mfa", "sso", "identity", "iam", "ldap", "ad ", "active directory",
          "keycloak", "okta", "cognito", "oauth", "idp", "login", "saml"]
    return any(
        any(k in n.get("label", "").lower() for k in kw)
        for n in nodes.values()
    )


def _arch_has_direct_workstation_to_db(nodes: Dict[str, Dict], edges: List[Dict]) -> bool:
    """Return True if any workstation/client node connects to a database with no auth node between them."""
    workstation_ids = {
        nid for nid, n in nodes.items()
        if any(kw in n.get("label", "").lower() for kw in ["workstation", "laptop", "desktop", "pc", "endpoint", "worker"])
    }
    db_ids = {
        nid for nid, n in nodes.items()
        if any(kw in n.get("label", "").lower() for kw in ["database", "db", "sql", "postgres", "mysql", "mongo", "redis", "state"])
    }
    if not workstation_ids or not db_ids:
        return False
    # Build adjacency — any path from workstation to db within 2 hops
    direct_targets = {e.get("to") for e in edges if e.get("from") in workstation_ids}
    one_hop_targets = {e.get("to") for e in edges if e.get("from") in direct_targets}
    reachable = direct_targets | one_hop_targets
    return bool(reachable & db_ids)


def map_path_to_per_node_techniques(
    path: List[str],
    nodes: Dict[str, Dict],
    controls_present: List[str],
    rapids: Optional[Dict] = None,
    edges: Optional[List[Dict]] = None,
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

    has_backup   = _arch_has_backup_nodes(nodes)
    has_cloud    = _arch_has_cloud_nodes(nodes)
    has_internet = _arch_has_internet_nodes(nodes)

    # Absence-of-security detection — arch-level anti-pattern signals
    # These boost techniques the engine would miss by only looking at present nodes.
    has_perimeter    = _arch_has_perimeter_nodes(nodes)
    has_auth         = _arch_has_auth_nodes(nodes)
    has_ws_to_db     = _arch_has_direct_workstation_to_db(nodes, edges or [])
    no_perimeter     = has_internet and not has_perimeter
    no_auth          = has_internet and not has_auth

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
            rapids=rapids,
            has_backup=has_backup,
            has_cloud=has_cloud,
            has_internet=has_internet,
        )

        # ── Absence-of-security boosts ────────────────────────────────────────
        # Fire when the arch is missing expected security nodes — these are the
        # techniques critics consistently catch that the base engine misses.

        if no_perimeter and position in ("entry", "traversal"):
            # No firewall/WAF/gateway → recon is unrestricted at every hop
            for t in ["T1595", "T1590"]:
                if t not in techniques:
                    techniques.append(t)
                    logger.info(f"  [no-perimeter] {node_label}: added {t}")

        if no_auth and position in ("entry", "traversal"):
            # No auth node → credential abuse is trivially easy
            for t in ["T1078", "T1110"]:
                if t not in techniques:
                    techniques.append(t)
                    logger.info(f"  [no-auth] {node_label}: added {t}")

        if has_ws_to_db and any(kw in label_lower for kw in [
            "workstation", "laptop", "desktop", "pc", "endpoint", "worker",
        ]):
            # Workstation with direct DB reach → lateral movement is the first step
            for t in ["T1021", "T1570"]:
                if t not in techniques:
                    techniques.append(t)
                    logger.info(f"  [ws-to-db] {node_label}: added {t}")

        per_node_techniques[node_id] = techniques

        logger.info(f"Node {node_label} ({position}): {len(techniques)} techniques → {techniques}")

    # Attach technique_context as a sidecar — callers may read it via the returned dict
    # Access as per_node_techniques.get("__context__") without breaking existing consumers
    context = build_technique_context(per_node_techniques, path, nodes, controls_present, rapids)
    per_node_techniques["__context__"] = context  # type: ignore[assignment]

    return per_node_techniques


def get_all_techniques_from_path(per_node_map: Dict[str, List[str]]) -> List[str]:
    """Deduplicated flat list of techniques across all nodes (skips __context__ sidecar)."""
    all_techniques = []
    for node_id, techniques in per_node_map.items():
        if node_id == "__context__":
            continue
        all_techniques.extend(techniques)
    return list(dict.fromkeys(all_techniques))


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
        # Initial Access
        "T1190": "Initial Access", "T1133": "Initial Access",
        "T1566": "Initial Access", "T1078": "Initial Access",
        "T1199": "Initial Access", "T1195": "Initial Access",
        # Execution
        "T1059": "Execution", "T1203": "Execution",
        "T1106": "Execution", "T1648": "Execution",
        "T1610": "Execution",
        # Persistence
        "T1098": "Persistence", "T1136": "Persistence",
        # Privilege Escalation
        "T1068": "Privilege Escalation", "T1548": "Privilege Escalation",
        # Defense Evasion
        "T1562": "Defense Evasion", "T1070": "Defense Evasion",
        "T1578": "Defense Evasion", "T1027": "Defense Evasion",
        # Credential Access
        "T1110": "Credential Access", "T1556": "Credential Access",
        "T1552": "Credential Access", "T1555": "Credential Access",
        "T1212": "Credential Access", "T1557": "Credential Access",
        "T1621": "Credential Access", "T1040": "Credential Access",
        # Discovery
        "T1083": "Discovery", "T1046": "Discovery",
        "T1018": "Discovery", "T1082": "Discovery",
        "T1087": "Discovery", "T1613": "Discovery",
        # Lateral Movement
        "T1021": "Lateral Movement", "T1550": "Lateral Movement",
        # Collection
        "T1213": "Collection", "T1530": "Collection",
        "T1005": "Collection", "T1114": "Collection",
        "T1039": "Collection",
        # Command and Control
        "T1090": "Command and Control", "T1071": "Command and Control",
        "T1095": "Command and Control",
        # Exfiltration
        "T1567": "Exfiltration", "T1041": "Exfiltration",
        "T1048": "Exfiltration",
        # Impact
        "T1485": "Impact", "T1486": "Impact", "T1490": "Impact",
        "T1491": "Impact", "T1498": "Impact", "T1499": "Impact",
        "T1565": "Impact",
        # Lateral Movement
        "T1557": "Credential Access", "T1210": "Lateral Movement",
        "T1570": "Lateral Movement",
        # Collection
        "T1039": "Collection",        "T1614": "Discovery",
        # Execution / Cloud
        "T1610": "Execution",         "T1613": "Discovery",
        "T1648": "Execution",         "T1578": "Defense Evasion",
        # Persistence / Privilege Escalation
        "T1098": "Persistence",       "T1136": "Persistence",
        "T1212": "Credential Access",
        # Defense Evasion
        "T1027": "Defense Evasion",   "T1562": "Defense Evasion",
        "T1070": "Defense Evasion",
        # Discovery
        "T1018": "Discovery",         "T1087": "Discovery",
        "T1082": "Discovery",
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
