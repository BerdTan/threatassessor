"""
threat_scene_deepener.py - APT attribution and CVE enrichment for attack path risk scenarios.

Adds apt_evidence, cve_ids, kev_hits, and ransomware_linked to each AP's risk_scenario.
Fully deterministic — no LLM. Enrichment is additive; no existing fields are modified.

CVE strategy (two-gate quality filter):
  Gate 1 — CTID KEV→ATT&CK: technique→CVE mappings (technique-precise, ~550 CVEs, 155 T-codes)
  Gate 2 — CISA KEV metadata: confirms active exploitation + ransomware flag (1,619 CVEs)
  CVEs that pass both gates appear as kev_hits — actively exploited AND technique-matched.
  All CVE IDs (gate 1 only) appear in cve_ids for reference.
  Fallback — MITRE description regex: fires only when KEV data is unavailable.
"""

import re
import logging
from typing import Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from chatbot.modules.mitre import MitreHelper

logger = logging.getLogger(__name__)

_CVE_YEAR_RE = re.compile(r'CVE-(\d{4})-\d+')


def deepen_threat_scenes(
    ground_truth: Dict,
    mitre: "MitreHelper",
    max_groups: int = 3,
    max_cves: int = 5,
    min_cve_year: int = 2018,
) -> Dict:
    """
    Enrich each attack path's risk_scenario with:
      apt_evidence   — top APT groups by technique overlap (MITRE ATT&CK)
      cve_ids        — CVEs technique-matched via CTID KEV (or MITRE regex fallback)
      kev_hits       — subset of cve_ids confirmed actively exploited in CISA KEV
      ransomware_linked — True if any KEV hit is flagged for ransomware use

    Operates in-place and returns ground_truth for chaining.
    """
    from chatbot.modules.kev_helper import get_kev_helper
    kev = get_kev_helper()

    attack_paths = ground_truth.get("expected_attack_paths", [])
    enriched = 0

    for ap in attack_paths:
        techniques: List[str] = ap.get("techniques", [])
        if not techniques:
            continue

        rs = ap.setdefault("risk_scenario", {})

        rs["apt_evidence"] = _build_apt_evidence(techniques, mitre, max_groups)

        cve_ids, kev_hits, ransomware_linked = _collect_cves_with_kev(
            techniques, kev, mitre, max_cves, min_cve_year
        )
        rs["cve_ids"] = cve_ids
        rs["kev_hits"] = kev_hits
        rs["ransomware_linked"] = ransomware_linked
        enriched += 1

    logger.info(f"threat_scene_deepener: enriched {enriched}/{len(attack_paths)} attack paths")
    return ground_truth


def _build_apt_evidence(
    techniques: List[str],
    mitre: "MitreHelper",
    max_groups: int,
) -> Dict:
    """Score APT groups by technique overlap count. Returns top N ranked groups."""
    group_overlap: Dict[str, Dict] = {}

    for tech_id in techniques:
        for group in mitre.get_groups_by_technique(tech_id):
            gid = group["group_id"]
            if gid not in group_overlap:
                group_overlap[gid] = {
                    "group_id":           gid,
                    "group_name":         group["group_name"],
                    "aliases":            group.get("aliases", []),
                    "technique_overlap":  0,
                    "matched_techniques": [],
                }
            group_overlap[gid]["technique_overlap"] += 1
            group_overlap[gid]["matched_techniques"].append(tech_id)

    ranked = sorted(
        group_overlap.values(),
        key=lambda g: g["technique_overlap"],
        reverse=True,
    )[:max_groups]

    top_group: Optional[str] = None
    if ranked:
        g = ranked[0]
        aliases = [a for a in g.get("aliases", []) if a != g["group_name"]]
        alias_str = f" ({aliases[0]})" if aliases else ""
        top_group = f"{g['group_name']}{alias_str} ({g['group_id']})"

    return {
        "apt_groups":   ranked,
        "top_group":    top_group,
        "mitre_backed": bool(ranked),
    }


def _collect_cves_with_kev(
    techniques: List[str],
    kev,
    mitre: "MitreHelper",
    max_cves: int,
    min_year: int,
) -> tuple:
    """
    Returns (cve_ids, kev_hits, ransomware_linked).

    Primary path (KEV available):
      - CTID KEV: technique→CVE lookup, filtered to min_year
      - CISA KEV: cross-reference to get kev_hits (confirmed actively exploited)
      - Sort: ransomware-linked first, then by date_added newest-first

    Fallback path (KEV files not downloaded):
      - MITRE description regex (sparse — only ~6 techniques have CVE refs)
      - kev_hits = [], ransomware_linked = False
    """
    if kev.available:
        return _collect_cves_kev(techniques, kev, max_cves, min_year)
    else:
        cve_ids = _collect_cves_mitre_fallback(techniques, mitre, max_cves, min_year)
        return cve_ids, [], False


def _collect_cves_kev(
    techniques: List[str],
    kev,
    max_cves: int,
    min_year: int,
) -> tuple:
    seen: Dict[str, Dict] = {}  # cve_id → enriched entry

    for tech_id in techniques:
        for entry in kev.get_cves_for_technique(tech_id):
            cve_id = entry["cve_id"]
            if cve_id in seen:
                continue
            m = _CVE_YEAR_RE.match(cve_id)
            if not m or int(m.group(1)) < min_year:
                continue
            seen[cve_id] = entry

    # Sort: ransomware-linked first, then newest date_added
    def _sort_key(e):
        date = e.get("date_added", "")
        return (0 if e.get("ransomware") else 1, date)

    sorted_entries = sorted(seen.values(), key=_sort_key)[:max_cves]

    cve_ids = [e["cve_id"] for e in sorted_entries]

    kev_hits = [
        {
            "cve_id":           e["cve_id"],
            "vendor":           e.get("vendor", ""),
            "product":          e.get("product", ""),
            "date_added":       e.get("date_added", ""),
            "ransomware":       e.get("ransomware", False),
            "capability_group": e.get("capability_group", ""),
        }
        for e in sorted_entries if e.get("actively_exploited")
    ]

    ransomware_linked = any(e.get("ransomware") for e in sorted_entries)

    return cve_ids, kev_hits, ransomware_linked


def _collect_cves_mitre_fallback(
    techniques: List[str],
    mitre: "MitreHelper",
    max_cves: int,
    min_year: int,
) -> List[str]:
    """MITRE description regex — sparse fallback when KEV data not available."""
    seen: Dict[str, None] = {}
    for tech_id in techniques:
        for cve in mitre.get_cves_for_technique(tech_id):
            seen[cve.upper()] = None

    recent = [
        c for c in seen
        if (m := _CVE_YEAR_RE.match(c)) and int(m.group(1)) >= min_year
    ]
    return sorted(recent, key=lambda c: int(_CVE_YEAR_RE.match(c).group(1)), reverse=True)[:max_cves]
