"""
ADR Generator — one master ADR per attack path.

Each ADR represents the security decision for one attack path. Its controls are
grouped by hop (the node on the path where the control applies). This mirrors
how a security architect thinks: "For AP-1 (Users → WebApp → AppServer → DB),
what control goes at each hop and why?"

Controls are assigned to hops by matching their techniques against
per_node_techniques on the path. Controls with no technique match are assigned
to the most exposed hop (first hop with any technique).

Fully deterministic — no LLM calls.
"""
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Arch-type → pattern framing (used in narrative, not compliance standard)
_ARCH_FRAMING: Dict[str, str] = {
    "web_app":   "internet-facing web application",
    "ai_system": "AI/ML system with model and data pipeline",
    "cloud":     "cloud-hosted system with shared-responsibility boundaries",
    "iot":       "IoT system with physical and protocol attack surface",
    "generic":   "system with broad network attack surface",
}

# RAPIDS threat category → plain-English consequence
_RAPIDS_CONSEQUENCE: Dict[str, str] = {
    "ransomware":        "data encryption and service disruption requiring ransom payment",
    "application_vulns": "exploitation of application flaws for code execution or data theft",
    "phishing":          "credential theft enabling attacker foothold inside the network",
    "insider_threat":    "data theft, sabotage, or privilege misuse by authenticated users",
    "dos":               "service unavailability and SLA breach",
    "supply_chain":      "persistent backdoor from compromised third-party components",
    "apt":               "long-term persistence, lateral movement, and covert data exfiltration",
}

_DIR_FRAMING: Dict[str, str] = {
    "prevention":  "Block attack progression before exploitation",
    "detection":   "Identify malicious activity in progress",
    "response":    "Contain and recover from a successful breach",
    "isolate":     "Reduce blast radius by limiting access scope",
    "hardening":   "Reduce attack surface and remove unnecessary exposure",
    "governance":  "Enforce policy and accountability",
}

# MITRE technique → short readable name (fallback when MITRE data not loaded)
_TECH_SHORT: Dict[str, str] = {
    "T1059": "Command Execution",
    "T1078": "Valid Accounts",
    "T1133": "External Remote Services",
    "T1190": "Exploit Public-Facing Application",
    "T1203": "Exploitation for Client Execution",
    "T1213": "Data from Information Repositories",
    "T1005": "Data from Local System",
    "T1566": "Phishing",
    "T1567": "Exfiltration Over Web Service",
    "T1486": "Data Encrypted for Impact",
    "T1490": "Inhibit System Recovery",
    "T1485": "Data Destruction",
    "T1110": "Brute Force",
    "T1021": "Remote Services",
    "T1046": "Network Service Discovery",
    "T1548": "Abuse Elevation Control Mechanism",
    "T1068": "Exploitation for Privilege Escalation",
    "T1082": "System Information Discovery",
}


def _technique_name(tech_id: str) -> str:
    return _TECH_SHORT.get(tech_id, tech_id)


def _resolve_hop(
    control_rec: Dict,
    ap: Dict,
) -> Tuple[str, str]:
    """
    Return (node_name, node_id_label) — the hop on this AP where the control applies.

    Priority:
    1. Explicit placement field matches a node name on the path
    2. Control's techniques intersect per_node_techniques for a node
    3. First node on the path that has any techniques (most exposed)
    4. First node on the path (fallback)
    """
    path_nodes: List[str] = ap.get("path", [])
    per_node: Dict[str, List[str]] = ap.get("per_node_techniques", {})
    cr_techs: set = set(control_rec.get("techniques", []))
    placement: str = control_rec.get("placement") or ""

    # 1. Explicit placement substring match
    if placement:
        placement_lower = placement.lower()
        for node in path_nodes:
            if node.lower() in placement_lower or placement_lower in node.lower():
                return node, node

    # 2. Technique overlap
    for node in path_nodes:
        node_techs = set(per_node.get(node, []))
        if cr_techs & node_techs:
            return node, node

    # 3. First node with any techniques
    for node in path_nodes:
        if per_node.get(node):
            return node, node

    # 4. Fallback
    if path_nodes:
        return path_nodes[0], path_nodes[0]
    return "unknown", "unknown"


def _extract_risk_values(
    control_rec: Dict,
    residual_before: Dict,
    residual_after: Dict,
) -> Tuple[int, int, int, int]:
    """Return (original_risk, rb, ra, reduction)."""
    overall_before = int(residual_before.get("overall_residual", 50))
    overall_after = int(residual_after.get("overall_residual", 30))

    rapids_threats = control_rec.get("rapids_threats", [])
    per_threat_before = residual_before.get("per_threat", {})
    per_threat_after = residual_after.get("per_threat", {})

    initial_risks, rb_vals, ra_vals = [], [], []
    for threat in rapids_threats:
        tb = per_threat_before.get(threat, {})
        ta = per_threat_after.get(threat, {})
        if tb:
            initial_risks.append(int(tb.get("initial_risk", overall_before)))
            rb_vals.append(int(tb.get("residual_risk", overall_before)))
        if ta:
            ra_vals.append(int(ta.get("residual_risk", overall_after)))

    original_risk = max(initial_risks) if initial_risks else overall_before
    rb = max(rb_vals) if rb_vals else overall_before
    ra = min(ra_vals) if ra_vals else overall_after
    return original_risk, rb, ra, max(0, rb - ra)


def _build_hop_controls(
    ap: Dict,
    relevant_crs: List[Tuple[int, Dict]],
    residual_before: Dict,
    residual_after: Dict,
    all_control_recs: List[Dict],
) -> List[Dict]:
    """
    Group relevant controls by hop, returning a list of hop entries ordered
    along the attack path.
    """
    path_nodes: List[str] = ap.get("path", [])
    per_node: Dict[str, List[str]] = ap.get("per_node_techniques", {})

    # Bucket controls by resolved hop
    hop_bucket: Dict[str, List[Tuple[int, Dict]]] = defaultdict(list)
    for cr_idx, cr in relevant_crs:
        node, _ = _resolve_hop(cr, ap)
        hop_bucket[node].append((cr_idx, cr))

    # Emit hops in path order (only nodes that have at least one control or technique)
    hops = []
    for node in path_nodes:
        node_techs = per_node.get(node, [])
        controls_at_hop = hop_bucket.get(node, [])

        # Include hop if it has techniques (i.e., is an attack surface) — even if no control
        if not node_techs and not controls_at_hop:
            continue

        # Determine whether any detection control covers this hop
        has_detection = any(
            cr.get("dir_category") in ("detection", "detect", "response")
            for _, cr in controls_at_hop
        )
        has_prevention = any(
            cr.get("dir_category") in ("prevention", "isolate", "hardening")
            for _, cr in controls_at_hop
        )
        gap_note = None
        if node_techs and not controls_at_hop:
            gap_note = f"No control assigned — {len(node_techs)} technique(s) exposed ({', '.join(node_techs[:3])})"
        elif has_prevention and not has_detection:
            gap_note = "Prevention only — add detection to satisfy zero-trust verify principle"

        # Build control entries
        control_entries = []
        for _, cr in controls_at_hop:
            orig, rb, ra, reduction = _extract_risk_values(cr, residual_before, residual_after)
            techniques = cr.get("techniques", [])
            dir_cat = cr.get("dir_category", "prevention")
            threats = cr.get("rapids_threats", [])

            # Reason: what threat + technique is this blocking at this hop
            if techniques and threats:
                reason = (
                    f"At {node}, {cr['control'].title()} blocks "
                    f"{', '.join(_technique_name(t) for t in techniques[:2])} "
                    f"({', '.join(techniques[:2])}) — mitigates {', '.join(threats[:2])} risk"
                )
            elif threats:
                reason = f"At {node}, {cr['control'].title()} reduces {', '.join(threats[:2])} risk"
            else:
                reason = f"At {node}, {cr['control'].title()} reduces exposure"

            control_entries.append({
                "control": cr.get("control", "unknown"),
                "dir_category": dir_cat,
                "framing": _DIR_FRAMING.get(dir_cat, dir_cat.capitalize()),
                "priority": cr.get("priority", "medium"),
                "techniques_blocked": techniques,
                "threats_addressed": threats,
                "reason": reason,
                "risk_before": orig,
                "risk_after": ra,
                "risk_reduction": reduction,
            })

        hops.append({
            "node": node,
            "node_techniques": node_techs,
            "controls": control_entries,
            "gap_note": gap_note,
        })

    return hops


def generate_adrs_from_ground_truth(
    ground_truth: Dict,
    config: Optional[Dict] = None,
) -> List[Dict]:
    """
    Build one master ADR per attack path, grouping controls by hop.

    Mutates ground_truth in-place:
      - Sets `adr_id` on each attack_path entry (its master ADR)
      - Sets `architecture_decision_records` top-level list (one per AP)

    Returns the ADR list.
    """
    config = config or {}
    control_recs: List[Dict] = ground_truth.get("control_recommendations", [])
    attack_paths: List[Dict] = ground_truth.get("expected_attack_paths", [])
    residual_before: Dict = ground_truth.get("residual_risks_before", {})
    residual_after: Dict = ground_truth.get("residual_risks_after", {})
    rapids: Dict = ground_truth.get("rapids_assessment", {})
    arch_type: str = ground_truth.get("metadata", {}).get("architecture_type", "generic")
    arch_framing = _ARCH_FRAMING.get(arch_type, _ARCH_FRAMING["generic"])

    # Build a ranked list of active RAPIDS threats with scores for narrative.
    # Primary source: rapids_assessment.risk_score; fallback: residual_risks_before.per_threat.initial_risk
    per_threat_before: Dict = residual_before.get("per_threat", {})
    active_threats: List[Dict] = sorted(
        [
            {
                "category": cat,
                "score": int(
                    (v.get("risk_score") if v.get("risk_score") is not None
                     else per_threat_before.get(cat, {}).get("initial_risk", 0))
                    or 0
                ),
                "consequence": _RAPIDS_CONSEQUENCE.get(cat, cat),
            }
            for cat, v in rapids.items()
            if isinstance(v, dict) and cat != "_metadata"
        ],
        key=lambda x: x["score"],
        reverse=True,
    )
    # Drop zero-score threats (no data at all)
    active_threats = [t for t in active_threats if t["score"] > 0]

    # Build overall risk values for the ADR summary
    overall_before = int(residual_before.get("overall_residual", 0))
    overall_after = int(residual_after.get("overall_residual", 0))

    adrs: List[Dict] = []

    for ap_idx, ap in enumerate(attack_paths):
        ap_id = ap.get("id", f"AP-{ap_idx + 1}")
        tier = ap.get("criticality_tier", "UNKNOWN")
        path_nodes: List[str] = ap.get("path", [])
        ap_idx_set = {ap_idx}

        # Controls relevant to this AP: those whose attack_paths includes this index,
        # or (if attack_paths is empty on the control) all controls
        relevant_crs: List[Tuple[int, Dict]] = []
        for cr_idx, cr in enumerate(control_recs):
            cr_paths = cr.get("attack_paths", [])
            if not cr_paths or ap_idx in cr_paths:
                relevant_crs.append((cr_idx, cr))

        # Group controls by hop
        hops = _build_hop_controls(ap, relevant_crs, residual_before, residual_after, control_recs)

        # Threat actor + key technique — pulled from risk_scenario if already enriched,
        # otherwise derived directly from path entry and techniques (enricher runs after)
        rs = ap.get("risk_scenario", {})
        per_node: Dict[str, List[str]] = ap.get("per_node_techniques", {})
        entry_node = path_nodes[0] if path_nodes else ""
        entry_techs = per_node.get(entry_node, [])
        entry_lower = entry_node.lower()

        if rs.get("threat_actor"):
            threat_actor = rs["threat_actor"]
        elif any(k in entry_lower for k in ("internet", "user", "external", "public")):
            threat_actor = "External attacker (internet-facing entry)"
        elif any(k in entry_lower for k in ("insider", "employee", "staff", "internal")):
            threat_actor = "Insider / authenticated user"
        elif any(k in entry_lower for k in ("partner", "vendor", "supplier")):
            threat_actor = "Third-party / supply chain actor"
        else:
            threat_actor = f"Attacker via {entry_node}"

        if rs.get("exploited_vulnerability"):
            vuln = rs["exploited_vulnerability"]
        elif entry_techs:
            t = entry_techs[0]
            vuln = f"{_technique_name(t)} ({t}) at {entry_node}"
        else:
            vuln = f"unspecified technique at {entry_node}"

        # Context: build structured narrative fields
        entry = path_nodes[0] if path_nodes else "?"
        target = path_nodes[-1] if path_nodes else "?"
        path_str = " → ".join(path_nodes)
        hop_count = len(path_nodes) - 1

        unprotected_hops = [h for h in hops if not h["controls"]]
        prevention_only_hops = [
            h for h in hops
            if h["controls"]
            and not any(c.get("dir_category") in ("detection", "detect", "response") for c in h["controls"])
        ]

        # Detect detection gap across all hops
        all_dir_cats = {
            cr.get("dir_category", "")
            for _, cr in relevant_crs
        }
        has_any_detection = any(c in all_dir_cats for c in ("detection", "detect", "response"))

        # Top RAPIDS threats for this AP's controls
        ap_threat_cats: List[str] = sorted({
            t for _, cr in relevant_crs for t in cr.get("rapids_threats", [])
        })
        ap_active_threats = [t for t in active_threats if t["category"] in ap_threat_cats]

        # Build threat_scenario — one narrative paragraph (no compliance references)
        top_threat_names = [t["category"].replace("_", " ").title() for t in ap_active_threats[:3]]
        top_threat_str = (
            f"{', '.join(top_threat_names[:-1])} and {top_threat_names[-1]}"
            if len(top_threat_names) > 1
            else (top_threat_names[0] if top_threat_names else "multiple threats")
        )
        # Use impact from risk_scenario if available (set by narrative_enricher); else top RAPIDS consequence
        rs_impact = rs.get("impact", "")
        if rs_impact:
            consequence_str = rs_impact
        elif ap_active_threats:
            consequence_str = ap_active_threats[0]["consequence"]
        else:
            consequence_str = "data exfiltration and service disruption"

        threat_scenario = (
            f"An {threat_actor} targets this {arch_framing} by entering at {entry} "
            f"and traversing {hop_count} hop(s) to reach {target}. "
            f"The initial foothold exploits {vuln}. "
            f"If unchecked, the attacker can cause {consequence_str}. "
            f"This path is the primary vector for {top_threat_str} risk in this architecture."
        )

        # Gap summary — what is currently unprotected and what that means
        gap_parts = []
        if unprotected_hops:
            nodes_str = ", ".join(h["node"] for h in unprotected_hops)
            gap_parts.append(
                f"{len(unprotected_hops)} hop(s) have no control assigned "
                f"({nodes_str}) — an attacker can traverse these without any verification"
            )
        if prevention_only_hops:
            nodes_str = ", ".join(h["node"] for h in prevention_only_hops)
            gap_parts.append(
                f"{len(prevention_only_hops)} hop(s) rely on prevention only with no detection "
                f"({nodes_str}) — a bypass would be silent"
            )
        if not has_any_detection:
            gap_parts.append(
                "no detection or response control exists anywhere on this path — "
                "a successful compromise would remain undetected"
            )
        gap_summary = "; ".join(gap_parts) if gap_parts else "All hops are covered with at least one control."

        # Decision rationale — why controls are required and what the outcome is
        control_count = sum(len(h["controls"]) for h in hops)
        decision_rationale = (
            f"The {control_count} control(s) below are required to reduce risk "
            f"from {overall_before} to {overall_after} across this path. "
            f"Each control is placed at the hop where the relevant technique is exercised, "
            f"following the zero-trust principle that every hop must be explicitly verified. "
            f"Priority is set by RAPIDS threat score — "
            f"the highest-scoring threat ({ap_active_threats[0]['category'].replace('_',' ')} at "
            f"{ap_active_threats[0]['score']}/100) drives the most critical controls."
            if ap_active_threats else
            f"The {control_count} control(s) below reduce risk from {overall_before} to {overall_after}. "
            f"Each is placed at the hop where the relevant technique is exercised."
        )

        new_risks = []
        if not has_any_detection:
            new_risks.append(
                "No detection or response control across this path — "
                "a successful compromise would be silent"
            )

        adr = {
            "adr_id": f"ADR-{ap_idx + 1:02d}",
            "attack_path_id": ap_id,
            "attack_path_tier": tier,
            "attack_path": path_str,
            "status": "proposed",
            "context": {
                "threat_scenario": threat_scenario,
                "gap_summary": gap_summary,
                "decision_rationale": decision_rationale,
                "active_threats": ap_active_threats,
                "threat_actor": threat_actor,
                "exploited_vulnerability": vuln,
                "attack_paths_affected": [ap_id],
            },
            "hops": hops,
            "consequences": {
                "overall_risk_before": overall_before,
                "overall_risk_after": overall_after,
                "risk_reduction_pct": (
                    round((overall_before - overall_after) / overall_before * 100)
                    if overall_before > 0 else 0
                ),
                "new_risks_introduced": new_risks,
            },
        }
        adrs.append(adr)

        # Back-link: stamp adr_id on the attack_path
        ap["adr_id"] = adr["adr_id"]
        # Keep adr_ids list for backward compat with other parts of the codebase
        ap["adr_ids"] = [adr["adr_id"]]

    ground_truth["architecture_decision_records"] = adrs
    logger.info(
        f"ADR Generator: generated {len(adrs)} master ADRs "
        f"(one per attack path) for {arch_type} architecture"
    )
    return adrs
