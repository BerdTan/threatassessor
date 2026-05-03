"""
Residual Risk Assessment Module

Calculates residual risk after implementing recommended controls.

Key Principle: No Silver Bullet
- Controls reduce risk but don't eliminate it (zero-days, APTs, insider threats)
- Business owners need to accept residual risk
- Transparent about control effectiveness limitations

Formula:
    Residual Risk = Initial Risk × (1 - Control Effectiveness)

Thresholds:
    < 10: ACCEPT (low risk, quarterly monitoring)
    10-20: MONITOR (medium risk, active monitoring)
    > 20: MITIGATE (high risk, additional controls needed)
"""

import logging
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


# ============================================================================
# CONTROL EFFECTIVENESS (Conservative Estimates)
# ============================================================================
#
# Based on industry standards and zero-trust principles:
# - Prevention controls can be bypassed (zero-days, advanced techniques)
# - Detection controls may miss sophisticated attacks
# - Isolation controls can be circumvented
# - Response controls depend on timely execution
#
# These are STARTING values - should be validated through:
# - Penetration testing
# - Red team exercises
# - Incident response analysis
# - Continuous improvement
# ============================================================================

CONTROL_EFFECTIVENESS = {
    # PREVENTION (70-90%): Controls that STOP attacks
    "prevention": {
        "waf": 0.70,                      # Blocks known exploits, not zero-days
        "mfa": 0.85,                      # Strong but social engineering possible
        "firewall": 0.75,                 # Blocks connections, but misconfiguration risk
        "input validation": 0.80,         # Stops many injections, but bypass possible
        "rate limiting": 0.80,            # Prevents brute force, but distributed attacks harder
        "edr": 0.85,                      # Catches malware, but advanced threats evade
        "patch management": 0.75,         # Closes known vulns, zero-days remain
        "encryption": 0.90,               # Strong data protection if keys secured
        "access control": 0.80,           # Limits access, but privilege escalation possible
        "antivirus": 0.60,                # Signature-based, misses new malware
        "api gateway": 0.75,              # Validates requests, logic flaws remain
        "ddos protection": 0.80,          # Mitigates floods, sophisticated attacks harder
        "database firewall": 0.75,        # Blocks malicious queries, stored procs harder
        "email gateway": 0.70,            # Filters phishing, targeted attacks get through
        "password policy": 0.65,          # Reduces weak passwords, credential theft remains
        "sso": 0.75,                      # Centralizes auth, single point of failure
        "device hardening": 0.70,         # Reduces attack surface, not foolproof
        "code review": 0.75,              # Catches bugs, subtle logic flaws missed
        "network segmentation": 0.75,     # Limits lateral movement, pivoting possible
    },

    # DETECTION (60-80%): Know attack is happening (assume prevention failed)
    "detect": {
        "logging": 0.60,                  # Records events, but analysis needed
        "ids": 0.70,                      # Detects patterns, encrypted traffic missed
        "siem": 0.75,                     # Correlates events, tuning required
        "anomaly detection": 0.65,        # Flags unusual, false positives high
        "behavioral analysis": 0.70,      # Profiles normal, slow attacks blend in
        "dlp": 0.70,                      # Monitors data, encrypted exfil missed
        "file integrity monitoring": 0.75, # Detects changes, rootkits can hide
        "application logging": 0.65,      # Captures app events, noise high
        "network monitoring": 0.70,       # Sees traffic, encrypted payloads opaque
        "audit logging": 0.65,            # Records actions, ex-filtration after compromise
        "error monitoring": 0.60,         # Catches failures, not all attacks fail
        "health checks": 0.70,            # Detects failures, doesn't prevent
        "performance monitoring": 0.65,   # Sees degradation, not root cause
        "security awareness training": 0.60, # Reduces mistakes, determined insiders bypass
        "threat intelligence": 0.70,      # Warns of threats, zero-days unknown
        "vulnerability assessment": 0.65, # Identifies weaknesses, exploitation depends
        "vulnerability scanning": 0.70,   # Finds known issues, zero-days missed (same as assessment)
    },

    # ISOLATION (50-70%): Contain the breach (limit damage)
    "isolate": {
        "least privilege": 0.70,          # Limits damage, privilege escalation possible
        "network segmentation": 0.65,     # Contains breach, pivoting possible
        "rbac": 0.70,                     # Enforces permissions, misconfiguration risk
        "container isolation": 0.65,      # Sandboxes apps, escape possible
        "circuit breaker": 0.60,          # Stops cascading, doesn't fix root cause
        "vlan": 0.65,                     # Segments network, VLAN hopping possible
        "dmz": 0.70,                      # Isolates services, pivot to internal possible
        "quarantine": 0.75,               # Isolates infected, before detection delay
        "session timeout": 0.60,          # Limits exposure window, active session risk
        "account lockout": 0.65,          # Stops brute force, DoS vector
        "acl": 0.65,                      # Controls access, misconfiguration common
        "backup isolation": 0.75,         # Protects backups, if not found first
        "data classification": 0.60,      # Labels sensitive, enforcement needed
        "column-level encryption": 0.70,  # Protects fields, key management critical
        "timeout policies": 0.60,         # Limits impact, doesn't prevent
        "queue management": 0.55,         # Controls load, sophisticated attacks adapt
    },

    # RESPONSE (40-60%): Recover from breach (damage already done)
    "respond": {
        "backup": 0.85,                   # Strong recovery IF tested regularly
        "incident response": 0.50,        # Mitigates damage, but after breach
        "auto-rollback": 0.60,            # Reverts changes, data loss possible
        "password reset": 0.55,           # Secures account, after compromise
        "auto-scaling": 0.60,             # Adds capacity, cost/attack vector
        "failover": 0.70,                 # Switches to backup, if configured
        "restart policies": 0.55,         # Recovers service, doesn't fix vuln
        "device reimaging": 0.75,         # Clean slate, data loss
        "data recovery": 0.70,            # Restores data, if backups clean
        "forensics": 0.45,                # Understands attack, after damage done
        "ip blocking": 0.50,              # Stops attacker, new IPs available
        "traffic filtering": 0.55,        # Blocks patterns, encryption bypasses
        "packet capture": 0.45,           # Records evidence, doesn't prevent
        "patch deployment": 0.65,         # Fixes vuln, after exploitation
        "account recovery": 0.60,         # Restores access, compromise impact remains
        "self-healing": 0.60,             # Auto-recovers, doesn't prevent recurrence
        "chaos engineering": 0.50,        # Tests resilience, doesn't guarantee
        "retry with backoff": 0.50,       # Handles transient, not persistent issues
    }
}

# Default effectiveness if control not found
DEFAULT_EFFECTIVENESS = {
    "prevention": 0.70,
    "detect": 0.60,
    "isolate": 0.55,
    "respond": 0.50
}


# ============================================================================
# RESIDUAL RISK CALCULATION
# ============================================================================

def get_control_effectiveness(control_name: str, dir_category: str) -> float:
    """
    Get effectiveness percentage for a control.

    Args:
        control_name: Control name (e.g., "waf", "mfa")
        dir_category: prevention, detect, isolate, or respond

    Returns:
        Effectiveness as decimal (0.0-1.0)
    """
    control_lower = control_name.lower()
    category_controls = CONTROL_EFFECTIVENESS.get(dir_category, {})

    # Exact match
    if control_lower in category_controls:
        return category_controls[control_lower]

    # Partial match (e.g., "web application firewall" matches "waf")
    for key, value in category_controls.items():
        if key in control_lower or control_lower in key:
            return value

    # Default by category
    return DEFAULT_EFFECTIVENESS.get(dir_category, 0.50)


def calculate_residual_risk_for_threat(
    threat_category: str,
    initial_risk: int,
    relevant_controls: List[Dict]
) -> Dict:
    """
    Calculate residual risk for a single RAPIDS threat category.

    Args:
        threat_category: e.g., "application_vulns", "ransomware"
        initial_risk: Initial RAPIDS risk score (0-100)
        relevant_controls: List of controls addressing this threat

    Returns:
        {
            "threat": "application_vulns",
            "initial_risk": 80,
            "controls": [{"name": "WAF", "effectiveness": 0.70, "type": "prevention"}, ...],
            "combined_effectiveness": 0.85,
            "residual_risk": 12,
            "status": "ACCEPT",
            "rationale": "..."
        }
    """
    if not relevant_controls or initial_risk == 0:
        return {
            "threat": threat_category,
            "initial_risk": initial_risk,
            "controls": [],
            "combined_effectiveness": 0.0,
            "residual_risk": initial_risk,
            "status": "MITIGATE",
            "rationale": "No controls implemented"
        }

    # Calculate combined effectiveness (multiple controls)
    # Formula: 1 - (1 - e1) × (1 - e2) × ... × (1 - en)
    # This accounts for independent controls providing layered defense

    control_details = []
    failure_probability = 1.0  # Probability all controls fail

    for ctrl in relevant_controls:
        control_name = ctrl.get("control", "")
        dir_category = ctrl.get("dir_category", "prevention")

        effectiveness = get_control_effectiveness(control_name, dir_category)
        control_details.append({
            "name": control_name,
            "effectiveness": effectiveness,
            "type": dir_category
        })

        # Multiply failure probabilities
        failure_probability *= (1.0 - effectiveness)

    combined_effectiveness = 1.0 - failure_probability
    residual_risk = int(initial_risk * failure_probability)

    # Determine status based on thresholds
    if residual_risk < 10:
        status = "ACCEPT"
        rationale = "Low residual risk - acceptable with quarterly monitoring"
    elif residual_risk < 20:
        status = "MONITOR"
        rationale = "Medium residual risk - requires active monitoring and quarterly review"
    else:
        status = "MITIGATE"
        rationale = "High residual risk - additional controls recommended"

    return {
        "threat": threat_category,
        "initial_risk": initial_risk,
        "controls": control_details,
        "combined_effectiveness": round(combined_effectiveness, 3),
        "residual_risk": residual_risk,
        "status": status,
        "rationale": rationale
    }


def map_present_controls_to_rapids(
    controls_present: set,
    rapids_assessment: Dict,
    attack_paths: List[Dict]
) -> List[Dict]:
    """
    Map present controls to RAPIDS threats they address.

    This creates control recommendation-like structure for present controls
    so we can calculate BEFORE residual risk.

    Args:
        controls_present: Set of controls already in architecture
        rapids_assessment: RAPIDS risk scores per category
        attack_paths: Attack paths (for context)

    Returns:
        List of control dicts with RAPIDS threat mappings
    """
    from chatbot.modules.rapids_driven_controls import RAPIDS_MANDATORY_CONTROLS

    # Build reverse mapping: control → RAPIDS threats it addresses
    control_to_rapids = {}
    for threat_type, priority_controls in RAPIDS_MANDATORY_CONTROLS.items():
        for priority in ["critical", "high", "medium"]:
            for control, rationale in priority_controls.get(priority, []):
                if control not in control_to_rapids:
                    control_to_rapids[control] = []
                control_to_rapids[control].append(threat_type)

    # Map present controls to RAPIDS threats
    present_mappings = []
    for control in controls_present:
        control_lower = control.lower()

        # Find matching RAPIDS threats
        matched_threats = []
        for control_key, threats in control_to_rapids.items():
            if control_key in control_lower or control_lower in control_key:
                matched_threats.extend(threats)

        # Remove duplicates
        matched_threats = list(set(matched_threats))

        if matched_threats:
            # Determine DIR category (prevention, detect, isolate, respond)
            dir_category = "prevention"  # Default
            if any(kw in control_lower for kw in ["log", "monitor", "siem", "ids", "alert"]):
                dir_category = "detect"
            elif any(kw in control_lower for kw in ["segment", "privilege", "rbac", "isolat", "contain"]):
                dir_category = "isolate"
            elif any(kw in control_lower for kw in ["backup", "recover", "restore", "incident", "response"]):
                dir_category = "respond"

            present_mappings.append({
                "control": control,
                "rapids_threats": matched_threats,
                "dir_category": dir_category,
                "mitigations": [],
                "techniques": [],
                "attack_paths": []
            })

    return present_mappings


def calculate_residual_risks(
    rapids_assessment: Dict,
    control_recommendations: List[Dict]
) -> Dict:
    """
    Calculate residual risk for all RAPIDS threat categories.

    Args:
        rapids_assessment: RAPIDS risk scores per category
        control_recommendations: List of recommended controls with RAPIDS context

    Returns:
        {
            "per_threat": {
                "application_vulns": {...},
                "ransomware": {...},
                ...
            },
            "overall_residual": 18.5,
            "overall_status": "MONITOR",
            "summary": "..."
        }
    """
    logger.info("Calculating residual risk assessment...")

    # Group controls by RAPIDS threat they address
    threat_to_controls = {}
    for ctrl in control_recommendations:
        rapids_threats = ctrl.get("rapids_threats", [])
        for threat in rapids_threats:
            if threat not in threat_to_controls:
                threat_to_controls[threat] = []
            threat_to_controls[threat].append(ctrl)

    # Calculate residual risk per threat
    per_threat_residual = {}
    residual_risks = []

    for threat_category, threat_data in rapids_assessment.items():
        # Skip metadata
        if threat_category.startswith("_") or not isinstance(threat_data, dict):
            continue

        if "risk" not in threat_data:
            continue

        initial_risk = threat_data.get("risk", 0)
        relevant_controls = threat_to_controls.get(threat_category, [])

        residual = calculate_residual_risk_for_threat(
            threat_category,
            initial_risk,
            relevant_controls
        )

        per_threat_residual[threat_category] = residual
        residual_risks.append(residual["residual_risk"])

        logger.info(f"  {threat_category}: {initial_risk}/100 → {residual['residual_risk']}/100 "
                   f"(effectiveness: {residual['combined_effectiveness']:.0%}, status: {residual['status']})")

    # Calculate overall residual risk
    overall_residual = sum(residual_risks) / len(residual_risks) if residual_risks else 0

    if overall_residual < 10:
        overall_status = "ACCEPT"
        summary = "Overall residual risk is LOW - acceptable for production with quarterly monitoring"
    elif overall_residual < 20:
        overall_status = "MONITOR"
        summary = "Overall residual risk is MEDIUM - requires active monitoring and quarterly reviews"
    else:
        overall_status = "MITIGATE"
        summary = "Overall residual risk is HIGH - additional controls strongly recommended"

    logger.info(f"Overall residual risk: {overall_residual:.1f}/100 ({overall_status})")

    return {
        "per_threat": per_threat_residual,
        "overall_residual": round(overall_residual, 1),
        "overall_status": overall_status,
        "summary": summary,
        "thresholds": {
            "accept": "< 10 (low risk)",
            "monitor": "10-20 (medium risk)",
            "mitigate": "> 20 (high risk)"
        }
    }
