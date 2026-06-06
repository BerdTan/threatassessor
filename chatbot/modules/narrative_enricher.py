"""
Narrative Enricher — adds risk_scenario per attack path and mitigation_narrative per control.

Template-first, deterministic by default. LLM polish is config-gated (default off).
Also assigns adr_ids to each AP by cross-referencing existing architecture_decision_records.
"""
from __future__ import annotations

import logging
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# RAPIDS category → impact language
_RAPIDS_IMPACT: Dict[str, str] = {
    "ransomware":         "service disruption, data encryption, and ransom extortion",
    "application_vulns":  "data exfiltration and remote code execution",
    "phishing":           "credential theft and initial foothold for further compromise",
    "insider_threat":     "data theft, sabotage, and privilege misuse",
    "dos":                "service unavailability and SLA breach",
    "supply_chain":       "persistent backdoor and integrity compromise of downstream systems",
    "apt":                "long-term persistence, reconnaissance, and data exfiltration",
}

# Exposure / entry node label → threat actor framing
_ACTOR_FROM_EXPOSURE: Dict[str, str] = {
    "external":   "External threat actor (internet-facing)",
    "internal":   "Insider threat (authenticated user)",
    "partner":    "Third-party / supply chain actor",
    "cloud":      "Cloud-based attacker (misconfiguration exploit)",
    "unknown":    "Unattributed threat actor",
}

# Target sensitivity tier → asset criticality label
_SENSITIVITY_LABEL: Dict[str, str] = {
    "critical":  "Critical asset (PII / financial / regulated data)",
    "high":      "High-value asset (internal IP / sensitive config)",
    "medium":    "Medium-sensitivity asset (operational data)",
    "low":       "Low-sensitivity asset (public-facing)",
    "unknown":   "Asset of unknown sensitivity",
}

# Fallback MITRE technique name when lookup unavailable
_TECHNIQUE_FALLBACK = "Unspecified technique"


# Fallback technique name map (same as adr_generator)
_TECH_SHORT: Dict[str, str] = {
    "T1059": "Command Execution",
    "T1078": "Valid Accounts",
    "T1110": "Brute Force",
    "T1021": "Remote Services",
    "T1046": "Network Service Discovery",
    "T1068": "Exploitation for Privilege Escalation",
    "T1082": "System Information Discovery",
    "T1133": "External Remote Services",
    "T1190": "Exploit Public-Facing Application",
    "T1203": "Exploitation for Client Execution",
    "T1213": "Data from Information Repositories",
    "T1005": "Data from Local System",
    "T1476": "Deliver Malicious App via Authorized App Store",
    "T1548": "Abuse Elevation Control Mechanism",
    "T1566": "Phishing",
    "T1567": "Exfiltration Over Web Service",
    "T1486": "Data Encrypted for Impact",
    "T1490": "Inhibit System Recovery",
    "T1485": "Data Destruction",
}


def _lookup_technique_name(technique_id: str, gt: Dict) -> str:
    """Derive a readable technique name — checks per_node_techniques dicts, then fallback map."""
    for ap in gt.get("expected_attack_paths", []):
        for node_techs in ap.get("per_node_techniques", {}).values():
            for t in node_techs:
                if isinstance(t, dict):
                    if t.get("technique_id") == technique_id or t.get("id") == technique_id:
                        return t.get("name", technique_id)
    return _TECH_SHORT.get(technique_id, technique_id)


def _build_risk_scenario(ap: Dict, gt: Dict) -> Dict:
    """Derive risk_scenario from structured attack path fields."""
    metadata = gt.get("metadata", {})
    exposure = metadata.get("exposure", "unknown")

    # Threat actor — derive from exposure metadata, then refine from entry node label
    threat_actor = _ACTOR_FROM_EXPOSURE.get(exposure, _ACTOR_FROM_EXPOSURE["unknown"])
    entry_label = ap.get("entry", "") or (ap.get("path", [""])[0])
    entry_lower = entry_label.lower()
    if "insider" in entry_lower or "employee" in entry_lower or "staff" in entry_lower:
        threat_actor = _ACTOR_FROM_EXPOSURE["internal"]
    elif "partner" in entry_lower or "vendor" in entry_lower or "supplier" in entry_lower:
        threat_actor = _ACTOR_FROM_EXPOSURE["partner"]
    elif "internet" in entry_lower or "user" in entry_lower or "external" in entry_lower or "public" in entry_lower:
        threat_actor = "External attacker (internet-facing entry)"
    elif "cloud" in entry_lower:
        threat_actor = _ACTOR_FROM_EXPOSURE["cloud"]
    elif threat_actor == _ACTOR_FROM_EXPOSURE["unknown"] and entry_label and entry_label not in ("", "unknown"):
        threat_actor = f"Attacker via {entry_label}"

    # Targeted asset
    target_node = ap.get("target", "unknown target")
    target_sensitivity = "unknown"
    # Check RAPIDS risk categories for clues on target sensitivity
    rapids = gt.get("rapids_assessment", {})
    top_risk = max(
        ((k, v.get("risk_score", 0)) for k, v in rapids.items() if isinstance(v, dict)),
        key=lambda x: x[1],
        default=(None, 0),
    )
    if top_risk[1] >= 80:
        target_sensitivity = "critical"
    elif top_risk[1] >= 60:
        target_sensitivity = "high"
    elif top_risk[1] >= 40:
        target_sensitivity = "medium"
    else:
        target_sensitivity = "low"
    targeted_asset = f"{target_node} ({_SENSITIVITY_LABEL.get(target_sensitivity, target_sensitivity)})"

    # Exploited vulnerability — first technique on the entry hop
    techniques: List[str] = ap.get("techniques", [])
    if techniques:
        first_tech = techniques[0]
        tech_name = _lookup_technique_name(first_tech, gt)
        exploited_vulnerability = f"{tech_name} ({first_tech}) at {ap.get('entry', 'entry node')}"
    else:
        exploited_vulnerability = f"Unspecified technique at {ap.get('entry', 'entry node')}"

    # Impact — from RAPIDS categories of highest-risk threats
    rapids_top = [k for k, v in sorted(
        ((k, v.get("risk_score", 0)) for k, v in rapids.items() if isinstance(v, dict)),
        key=lambda x: x[1], reverse=True
    )[:2]]
    impact_parts = [_RAPIDS_IMPACT.get(cat, cat) for cat in rapids_top]
    impact = "; ".join(impact_parts) if impact_parts else "data breach and service disruption"

    return {
        "threat_actor": threat_actor,
        "targeted_asset": targeted_asset,
        "exploited_vulnerability": exploited_vulnerability,
        "impact": impact,
    }


def _build_mitigation_narrative(cr: Dict, ap_ids: List[str], rr_before: Dict, rr_after: Dict) -> str:
    """Derive a plain-language mitigation_narrative for a control recommendation."""
    control = cr.get("control", "this control").title()
    placement = cr.get("placement", "unspecified layer")
    techniques = cr.get("techniques", [])
    tech_str = ", ".join(techniques[:3]) if techniques else "identified techniques"
    paths_str = ", ".join(ap_ids[:3]) + (" + more" if len(ap_ids) > 3 else "")

    overall_before = int(rr_before.get("overall_residual", 0))
    overall_after = int(rr_after.get("overall_residual", 0))
    status_after = rr_after.get("overall_status", "MONITOR")

    partial_exposure = ""
    # Flag if not all APs are covered
    all_ap_count = len(cr.get("attack_paths", []))
    covered_count = len(ap_ids)
    if all_ap_count > covered_count:
        partial_exposure = f" Note: {all_ap_count - covered_count} additional attack path(s) not fully covered."

    return (
        f"{control} at {placement} addresses {tech_str} ({paths_str}). "
        f"Residual drops {overall_before}→{overall_after} "
        f"(→{status_after}).{partial_exposure}"
    )


def enrich_ground_truth(ground_truth: Dict, config: Optional[Dict] = None) -> Dict:
    """
    Add risk_scenario to each attack path and mitigation_narrative to each control rec.

    If architecture_decision_records is present, also stamps adr_ids on each AP.
    Mutates ground_truth in-place and returns it.
    """
    config = config or {}
    attack_paths: List[Dict] = ground_truth.get("expected_attack_paths", [])
    control_recs: List[Dict] = ground_truth.get("control_recommendations", [])
    rr_before: Dict = ground_truth.get("residual_risks_before", {})
    rr_after: Dict = ground_truth.get("residual_risks_after", {})
    adrs: List[Dict] = ground_truth.get("architecture_decision_records", [])

    # Build AP id→index for adr_ids lookup
    ap_id_to_idx: Dict[str, int] = {
        ap.get("id", f"AP-{i+1}"): i for i, ap in enumerate(attack_paths)
    }

    # Enrich each attack path
    for ap in attack_paths:
        if "risk_scenario" not in ap:
            ap["risk_scenario"] = _build_risk_scenario(ap, ground_truth)

    # Assign adr_ids to each AP from existing ADRs (if not already done by adr_generator)
    if adrs:
        for ap in attack_paths:
            if "adr_ids" not in ap:
                ap_id = ap.get("id", "")
                ap["adr_ids"] = [
                    adr["adr_id"]
                    for adr in adrs
                    if ap_id in adr.get("context", {}).get("attack_paths_affected", [])
                ]

    # Enrich each control recommendation
    for cr_index, cr in enumerate(control_recs):
        if "mitigation_narrative" not in cr:
            # Derive ap_ids for this control
            ap_idx_list = cr.get("attack_paths", [])
            ap_ids = [
                attack_paths[idx].get("id", f"AP-{idx+1}")
                for idx in ap_idx_list
                if isinstance(idx, int) and 0 <= idx < len(attack_paths)
            ] or [ap.get("id", f"AP-{i+1}") for i, ap in enumerate(attack_paths)]
            cr["mitigation_narrative"] = _build_mitigation_narrative(cr, ap_ids, rr_before, rr_after)

    logger.info(
        f"Narrative Enricher: enriched {len(attack_paths)} APs, "
        f"{len(control_recs)} controls"
    )
    return ground_truth
