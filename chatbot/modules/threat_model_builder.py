"""
Threat Model Builder — builds a pattern-aware threat_model block in ground_truth.

Template-first, fully deterministic. LLM polish is config-gated (default off).
Consumes enriched ground_truth (after narrative_enricher has run).
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# Pattern-specific threat focus per architecture type
_ARCH_FOCUS: Dict[str, Dict] = {
    "web_app": {
        "threat_focus": ["application_vulns", "phishing"],
        "primary_framing": "Perimeter defence: Initial Access and Exfiltration",
        "tactic_focus": ["Initial Access", "Exfiltration", "Credential Access"],
    },
    "ai_system": {
        "threat_focus": ["integrity", "privacy"],
        "primary_framing": "ARC Framework: Model integrity, data poisoning, and privacy",
        "tactic_focus": ["ML Attack", "Data Manipulation", "Inference Attack"],
    },
    "cloud": {
        "threat_focus": ["insider_threat", "application_vulns"],
        "primary_framing": "Cloud posture: Misconfiguration and lateral movement",
        "tactic_focus": ["Privilege Escalation", "Defense Evasion", "Lateral Movement"],
    },
    "iot": {
        "threat_focus": ["ransomware", "dos"],
        "primary_framing": "Physical + protocol: Lateral Movement and Impact",
        "tactic_focus": ["Lateral Movement", "Impact", "Initial Access"],
    },
    "generic": {
        "threat_focus": [],  # falls through to RAPIDS top-2
        "primary_framing": "Broad attack surface across all RAPIDS categories",
        "tactic_focus": [],
    },
}

# RAPIDS categories ranked for impact summary
_RAPIDS_SEVERITY_ORDER = [
    "ransomware", "apt", "supply_chain", "application_vulns",
    "insider_threat", "phishing", "dos",
]


def _top_rapids_categories(rapids: Dict, n: int = 2) -> List[str]:
    """Return the top-n RAPIDS categories by risk_score."""
    scored = [
        (cat, v.get("risk_score", 0))
        for cat, v in rapids.items()
        if isinstance(v, dict) and "risk_score" in v
    ]
    return [cat for cat, _ in sorted(scored, key=lambda x: x[1], reverse=True)[:n]]


def _find_architecture_weakness(attack_paths: List[Dict]) -> str:
    """Return the node appearing in most attack paths (pivot/bottleneck)."""
    node_counts: Counter = Counter()
    for ap in attack_paths:
        for node in ap.get("path", []):
            node_counts[node] += 1
    if not node_counts:
        return "unknown"
    return node_counts.most_common(1)[0][0]


def _find_trust_boundaries_at_risk(
    attack_paths: List[Dict],
    control_recs: List[Dict],
) -> List[str]:
    """
    Return nodes shared across 2+ paths where no detection/response control exists at that node.
    """
    # Build node → paths index
    node_to_paths: Dict[str, List[str]] = {}
    for ap in attack_paths:
        for node in ap.get("path", []):
            node_to_paths.setdefault(node, []).append(ap.get("id", "unknown"))

    # Nodes in 2+ paths = trust boundary candidates
    candidates = {node for node, paths in node_to_paths.items() if len(paths) >= 2}

    # Detection/response placements
    detect_placements = {
        cr.get("placement", "").lower()
        for cr in control_recs
        if cr.get("dir_category") in ("detection", "response")
    }

    # A candidate is "at risk" if no detect control targets that node
    at_risk = [
        node for node in sorted(candidates)
        if not any(node.lower() in p for p in detect_placements)
    ]
    return at_risk[:5]  # cap to avoid overwhelming output


def _build_summary(
    arch_type: str,
    highest_ap: Optional[Dict],
    weakness: str,
    top_rapids: List[str],
    pattern_framing: str,
) -> str:
    top_str = " and ".join(top_rapids) if top_rapids else "multiple threat categories"
    ap_desc = ""
    if highest_ap:
        ap_desc = (
            f" The highest-criticality path runs {highest_ap.get('entry', '?')} → "
            f"{highest_ap.get('target', '?')} ({highest_ap.get('criticality_tier', 'UNKNOWN')})."
        )
    return (
        f"{pattern_framing}.{ap_desc} "
        f"Primary risk drivers: {top_str}. "
        f"Architecture bottleneck: {weakness}."
    )


def build_threat_model(ground_truth: Dict, config: Optional[Dict] = None) -> Dict:
    """
    Build and inject a `threat_model` block into ground_truth.

    Returns the updated ground_truth (also mutated in-place).
    """
    config = config or {}
    attack_paths: List[Dict] = ground_truth.get("expected_attack_paths", [])
    control_recs: List[Dict] = ground_truth.get("control_recommendations", [])
    rapids: Dict = ground_truth.get("rapids_assessment", {})
    metadata: Dict = ground_truth.get("metadata", {})
    arch_type: str = metadata.get("architecture_type", "generic")

    arch_cfg = _ARCH_FOCUS.get(arch_type, _ARCH_FOCUS["generic"])

    # pattern_focus — use arch preset if defined, else RAPIDS top-2
    pattern_focus = arch_cfg["threat_focus"] or _top_rapids_categories(rapids, n=2)

    # architecture_weakness — node in most attack paths
    weakness = _find_architecture_weakness(attack_paths)

    # trust_boundaries_at_risk — multi-path nodes with no detect control
    trust_boundaries = _find_trust_boundaries_at_risk(attack_paths, control_recs)

    # highest_risk_scenario — risk_scenario from highest-criticality AP
    tier_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
    highest_ap = max(
        attack_paths,
        key=lambda ap: tier_order.get(ap.get("criticality_tier", "LOW"), 0),
        default=None,
    )
    highest_risk_scenario = (
        highest_ap.get("risk_scenario") if highest_ap else None
    )

    # primary_threat_actor from highest AP risk_scenario
    primary_threat_actor = (
        highest_risk_scenario.get("threat_actor", "Unknown")
        if highest_risk_scenario
        else "Unknown"
    )

    # residual_risk_summary
    rr_before: Dict = ground_truth.get("residual_risks_before", {})
    rr_after: Dict = ground_truth.get("residual_risks_after", {})
    overall_before = int(rr_before.get("overall_residual", 0))
    overall_after = int(rr_after.get("overall_residual", 0))
    risk_reduction_pct = (
        round((overall_before - overall_after) / overall_before * 100)
        if overall_before > 0 else 0
    )

    per_ap_residual = []
    adrs: List[Dict] = ground_truth.get("architecture_decision_records", [])
    # Index master ADR by AP id for new per-AP ADR structure
    adr_by_ap_id: Dict[str, Dict] = {adr.get("attack_path_id", ""): adr for adr in adrs}
    for ap in attack_paths:
        ap_id = ap.get("id", "?")
        ap_adrs = ap.get("adr_ids", [])
        master_adr = adr_by_ap_id.get(ap_id)
        if master_adr:
            ap_residual = master_adr.get("consequences", {}).get("overall_risk_after", overall_after)
        else:
            ap_residual = overall_after
        per_ap_residual.append({
            "ap_id": ap_id,
            "criticality_before": ap.get("criticality_tier", "UNKNOWN"),
            "residual_after_adrs": ap_residual,
            "adrs_applied": ap_adrs,
        })

    residual_risk_summary = {
        "overall_before": overall_before,
        "overall_after_controls": overall_after,
        "risk_reduction_pct": risk_reduction_pct,
        "status_after": rr_after.get("overall_status", "MONITOR"),
        "per_ap_residual": per_ap_residual,
    }

    summary = _build_summary(
        arch_type,
        highest_ap,
        weakness,
        pattern_focus,
        arch_cfg["primary_framing"],
    )

    threat_model = {
        "architecture_type": arch_type,
        "pattern_focus": pattern_focus,
        "tactic_focus": arch_cfg["tactic_focus"],
        "summary": summary,
        "primary_threat_actor": primary_threat_actor,
        "highest_risk_scenario": highest_risk_scenario,
        "architecture_weakness": weakness,
        "trust_boundaries_at_risk": trust_boundaries,
        "residual_risk_summary": residual_risk_summary,
        "generated_by": "template",
    }

    ground_truth["threat_model"] = threat_model
    logger.info(
        f"Threat Model Builder: built threat_model for {arch_type} "
        f"({len(attack_paths)} APs, weakness={weakness})"
    )
    return ground_truth
