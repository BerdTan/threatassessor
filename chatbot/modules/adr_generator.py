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
import re
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


# Keywords that identify a node as a human/client/endpoint rather than a server-side component.
# Server-side controls (API Gateway, WAF, etc.) should not be placed here.
_USER_NODE_KEYWORDS: set = {
    "user", "users", "internet", "client", "clients", "browser",
    "mobile", "employee", "staff", "admin", "external", "partner",
    "vendor", "endpoint", "workstation", "attacker",
}

# Controls that are server-side / network-boundary by nature — never placed on a user/client node.
_SERVER_SIDE_CONTROLS: set = {
    "api gateway", "waf", "web application firewall", "reverse proxy",
    "load balancer", "firewall", "network segmentation", "dmz",
    "service mesh", "ingress controller",
}


def _is_user_node(node_id: str, node_label: str) -> bool:
    """Return True if this node represents a human/client origin, not a server component."""
    tokens = _node_tokens(node_id) + _node_tokens(node_label)
    return any(t in _USER_NODE_KEYWORDS for t in tokens)


# Zero-trust DIR categories required at every hop for full coverage.
_ZT_REQUIRED: List[str] = ["prevention", "detect", "isolate", "respond"]

# Canonical mapping: some dir_category values use alternate names
_ZT_NORMALISE: Dict[str, str] = {
    "prevention":  "prevention",
    "detect":      "detect",
    "detection":   "detect",
    "isolate":     "isolate",
    "response":    "respond",
    "respond":     "respond",
    "hardening":   "prevention",  # hardening strengthens prevention layer
    "governance":  "isolate",     # governance enforces access boundaries
}


def _zt_gap_note(controls: List[Dict]) -> Optional[str]:
    """
    Return a gap note if the hop does not satisfy zero-trust coverage
    (prevent + detect + isolate + respond), or None if fully covered.
    """
    covered = {_ZT_NORMALISE.get(c.get("dir_category", ""), "") for c in controls}
    covered.discard("")
    missing = [cat for cat in _ZT_REQUIRED if cat not in covered]
    if not missing:
        return None
    return (
        f"Zero-trust gap: missing {', '.join(missing)} layer(s). "
        f"Present: {', '.join(sorted(covered)) or 'none'}."
    )


def _node_tokens(name: str) -> List[str]:
    """Split a node ID or label into lowercase word tokens for fuzzy matching.

    'AppServer'         → ['app', 'server']
    'Application Server' → ['application', 'server']
    'WebApp'            → ['web', 'app']
    """
    # Split on spaces first, then on camelCase boundaries
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", name).split()
    return [p.lower() for p in parts if p]


def _placement_matches_node(placement: str, node_id: str, node_label: str) -> bool:
    """Return True if the placement string refers to this node.

    Checks (in order):
    1. Direct substring: node_id or node_label (lowercased) appears in placement
    2. Token overlap: all tokens from node_id appear in placement tokens
    3. Token overlap: all tokens from node_label appear in placement tokens
    """
    p = placement.lower()
    if node_id.lower() in p or node_label.lower() in p:
        return True
    p_tokens = set(_node_tokens(placement))
    if all(t in p_tokens for t in _node_tokens(node_id)):
        return True
    if node_label and all(t in p_tokens for t in _node_tokens(node_label)):
        return True
    return False


def _resolve_hop(
    control_rec: Dict,
    ap: Dict,
    parsed_nodes: Optional[Dict] = None,
) -> Tuple[str, str]:
    """
    Return (node_id, node_id) — the hop on this AP where the control applies.

    Priority:
    1. Explicit placement field — matches node ID or label (token-aware, camelCase-split)
    2. Control's techniques intersect per_node_techniques for a node
    3. First node on the path that has any techniques (most exposed)
    4. First node on the path (fallback)
    """
    path_nodes: List[str] = ap.get("path", [])
    per_node: Dict[str, List[str]] = ap.get("per_node_techniques", {})
    cr_techs: set = set(control_rec.get("techniques", []))
    placement: str = control_rec.get("placement") or ""
    parsed_nodes = parsed_nodes or {}

    ctrl_name = (control_rec.get("control") or "").lower()
    is_server_side = any(s in ctrl_name for s in _SERVER_SIDE_CONTROLS)

    # 1. Placement match — compare against both node ID and display label
    if placement:
        for node in path_nodes:
            label = parsed_nodes.get(node, {}).get("label", node)
            if _placement_matches_node(placement, node, label):
                # Skip user/client nodes for server-side controls even if placement matches
                if is_server_side and _is_user_node(node, label):
                    continue
                return node, node

    # 2. Technique overlap (skip user nodes for server-side controls)
    for node in path_nodes:
        label = parsed_nodes.get(node, {}).get("label", node)
        if is_server_side and _is_user_node(node, label):
            continue
        node_techs = set(per_node.get(node, []))
        if cr_techs & node_techs:
            return node, node

    # 2b. Technique overlap without server-side restriction (fallback for server-side controls
    #     when all non-user nodes lack those techniques)
    for node in path_nodes:
        node_techs = set(per_node.get(node, []))
        if cr_techs & node_techs:
            return node, node

    # 3. First non-user node with any techniques (server-side controls prefer server nodes)
    for node in path_nodes:
        label = parsed_nodes.get(node, {}).get("label", node)
        if is_server_side and _is_user_node(node, label):
            continue
        if per_node.get(node):
            return node, node

    # 4. First node with any techniques
    for node in path_nodes:
        if per_node.get(node):
            return node, node

    # 5. Fallback
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


def _classify_gap(
    node: str,
    node_techs: List[str],
    path_nodes: List[str],
    hop_bucket: Dict,
) -> Tuple[str, str]:
    """
    Return (gap_type, gap_note) for a hop that has techniques but no assigned control.

    gap_type values (machine-readable, used by MoE critics):
      "upstream_covered"  — a prior hop already has a control that blocks these techniques
      "library_gap"       — techniques are known but no control in the pattern library targets them
      "detection_only"    — only detection controls present, no prevention
      "unmitigated"       — no explanation found; genuine gap requiring critic review
    """
    node_tech_set = set(node_techs)
    node_idx = path_nodes.index(node) if node in path_nodes else -1
    tech_str = ", ".join(node_techs[:4])

    # Check if an earlier hop already covers all these techniques
    earlier_nodes = path_nodes[:node_idx]
    upstream_ctrls_for_techs: List[str] = []
    for prev_node in earlier_nodes:
        prev_ctrls = hop_bucket.get(prev_node, [])
        for _, cr in prev_ctrls:
            cr_techs = set(cr.get("techniques", []))
            overlap = cr_techs & node_tech_set
            if overlap:
                upstream_ctrls_for_techs.append(
                    f"{cr['control']} at {prev_node} covers {', '.join(overlap)}"
                )

    if upstream_ctrls_for_techs:
        note = (
            f"Techniques {tech_str} are present but assumed covered upstream: "
            + "; ".join(upstream_ctrls_for_techs[:2])
            + ". Verify upstream controls are effective at this depth."
        )
        return "upstream_covered", note

    # No upstream coverage — check if the techniques map to any known controls at all
    # (library gap: techniques exist but pattern library has no control targeting them here)
    return (
        "library_gap",
        f"No deterministic control maps to {tech_str} at {node}. "
        f"The pattern library does not cover this hop — "
        f"MoE critic should assess whether additional controls are feasible or risk must be accepted."
    )


def _build_hop_controls(
    ap: Dict,
    relevant_crs: List[Tuple[int, Dict]],
    residual_before: Dict,
    residual_after: Dict,
    all_control_recs: List[Dict],
    parsed_nodes: Optional[Dict] = None,
) -> List[Dict]:
    """
    Group relevant controls by hop, returning a list of hop entries ordered
    along the attack path.
    """
    path_nodes: List[str] = ap.get("path", [])
    per_node: Dict[str, List[str]] = ap.get("per_node_techniques", {})
    parsed_nodes = parsed_nodes or {}

    # Bucket controls by resolved hop (using label-aware placement matching)
    hop_bucket: Dict[str, List[Tuple[int, Dict]]] = defaultdict(list)
    for cr_idx, cr in relevant_crs:
        node, _ = _resolve_hop(cr, ap, parsed_nodes)
        hop_bucket[node].append((cr_idx, cr))

    # Emit hops in path order (only nodes that have at least one control or technique)
    hops = []
    for node in path_nodes:
        node_techs = per_node.get(node, [])
        controls_at_hop = hop_bucket.get(node, [])

        # Include hop if it has techniques (i.e., is an attack surface) — even if no control
        if not node_techs and not controls_at_hop:
            continue

        node_label = parsed_nodes.get(node, {}).get("label", node)
        gap_note = None
        gap_type = None
        if node_techs and not controls_at_hop:
            gap_type, gap_note = _classify_gap(node, node_techs, path_nodes, hop_bucket)

        # Build control entries
        control_entries = []
        for _, cr in controls_at_hop:
            orig, rb, ra, reduction = _extract_risk_values(cr, residual_before, residual_after)
            techniques = cr.get("techniques", [])
            dir_cat = cr.get("dir_category", "prevention")
            threats = cr.get("rapids_threats", [])

            # Reason: what threat + technique is this blocking at this hop (use display label)
            if techniques and threats:
                reason = (
                    f"At {node_label}, {cr['control'].title()} blocks "
                    f"{', '.join(_technique_name(t) for t in techniques[:2])} "
                    f"({', '.join(techniques[:2])}) — mitigates {', '.join(threats[:2])} risk"
                )
            elif threats:
                reason = f"At {node_label}, {cr['control'].title()} reduces {', '.join(threats[:2])} risk"
            else:
                reason = f"At {node_label}, {cr['control'].title()} reduces exposure"

            ssp_ctx = cr.get("ssp_context")
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
                "ssp_context": ssp_ctx,
            })

        # Full zero-trust coverage check for hops that have controls
        if control_entries and not gap_note:
            zt_note = _zt_gap_note(control_entries)
            if zt_note:
                gap_type = "detection_only"
                gap_note = zt_note

        hops.append({
            "node": node,
            "node_label": node_label,
            "node_techniques": node_techs,
            "controls": control_entries,
            "gap_note": gap_note,
            "gap_type": gap_type,
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
    # Node ID → {label, shape} — used for label-aware placement matching
    parsed_nodes: Dict = ground_truth.get("metadata", {}).get("parsed_nodes", {})

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
        hops = _build_hop_controls(ap, relevant_crs, residual_before, residual_after, control_recs, parsed_nodes)

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

        # Gap summary — classify each unprotected hop so the MoE critic knows exactly what it is
        gap_parts = []
        upstream_hops = [h for h in unprotected_hops if h.get("gap_type") == "upstream_covered"]
        library_gap_hops = [h for h in unprotected_hops if h.get("gap_type") == "library_gap"]
        unmitigated_hops = [h for h in unprotected_hops if h.get("gap_type") == "unmitigated"]

        if upstream_hops:
            gap_parts.append(
                f"{len(upstream_hops)} hop(s) ({', '.join(h['node'] for h in upstream_hops)}) "
                f"have no dedicated control but are assumed covered by upstream controls — "
                f"verify depth-of-defence is sufficient"
            )
        if library_gap_hops:
            gap_parts.append(
                f"{len(library_gap_hops)} hop(s) ({', '.join(h['node'] for h in library_gap_hops)}) "
                f"have exposed techniques with no matching control in the pattern library — "
                f"MoE critic required to assess feasibility or accept residual risk"
            )
        if unmitigated_hops:
            gap_parts.append(
                f"{len(unmitigated_hops)} hop(s) ({', '.join(h['node'] for h in unmitigated_hops)}) "
                f"are genuinely unmitigated — no upstream coverage and no library match"
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
