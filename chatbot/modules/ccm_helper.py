"""
CSA CCM Helper — Cloud Controls Matrix v4.1 → MITRE ATT&CK Mapping

Provides compliance control lookups based on the CTID Mappings Explorer data:
- 57 CCM controls spanning 17 capability groups
- 213 MITRE ATT&CK technique mappings
- SSRM (Shared Security Responsibility Model) layer annotation (heuristic)
- Best-effort SSP category prefix bridge (CCM group → SG SSP catalog category)

Data source: CTID Mappings Explorer (Apache 2.0)
Refresh: python3 scripts/data/fetch_ccm.py

Usage:
    ccm = get_ccm_helper()
    controls = ccm.get_controls_for_technique("T1078.004")
    controls = ccm.get_controls_for_techniques(["T1078.004", "T1530"])
    info = ccm.get_control_info("IAM-16")
    layer = ccm.get_ssrm_layer("IAM-16")  # "shared" | "csc" | "csp"
    ssp_prefixes = ccm.get_ssp_prefixes("AIS-08")  # ["as", "ac"]
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

_DATA_DIR = Path(__file__).parent.parent / "data" / "ccm"

# ---------------------------------------------------------------------------
# SSRM layer heuristic — not formally encoded in CCM data
# shared = both CSP and CSC must act; csc = consumer's responsibility; csp = provider's
# ---------------------------------------------------------------------------
_SSRM_LAYER: Dict[str, str] = {
    "IAM": "shared",   # Identity is always shared — both sides manage accounts
    "AIS": "csc",      # Application/API security is primarily the customer's code
    "STA": "shared",   # Supply chain is a shared concern
    "DSP": "shared",   # Data security spans both layers
    "IVS": "csc",      # Infrastructure virtualisation config — customer controls
    "SEF": "shared",   # Security events require both sides' logs
    "HRS": "csp",      # HR/onboarding policies — typically provider-side
    "GRC": "csp",      # Governance/compliance documentation — provider-side
    "BCR": "shared",   # Business continuity needs both
    "CCC": "csc",      # Change control is on the customer side
    "CEK": "shared",   # Crypto/encryption key management — shared
    "LOG": "shared",   # Logging — both must log their own systems
    "A&A": "csp",      # Audit & assurance — provider certification
    "DCS": "csp",      # Datacenter security — provider's physical infra
    "IPY": "shared",   # Interoperability — both sides
    "TVM": "shared",   # Threat/vulnerability management — both scan
    "I&S": "csc",      # Identity and access management (sub-group)
    "UEM": "csc",      # Unified endpoint management — customer devices
}

# ---------------------------------------------------------------------------
# CCM group → SG SSP catalog category prefix bridge (best-effort, informational)
# ---------------------------------------------------------------------------
_CCM_TO_SSP_PREFIX: Dict[str, List[str]] = {
    "IAM":  ["ac"],           # Access Control
    "AIS":  ["as", "ac"],     # Application Security + Access Control
    "STA":  ["sc", "as"],     # Software Supply Chain + Application Security
    "DSP":  ["dp", "ck"],     # Data Protection + Cryptography/Encryption
    "IVS":  ["is", "ns"],     # Infrastructure Security + Network Security
    "SEF":  ["lm", "rs"],     # Logging & Monitoring + Resiliency
    "HRS":  ["hr"],           # Human Resources
    "GRC":  ["pm"],           # Security Programme Management
    "BCR":  ["br"],           # Backup & Recovery
    "CCC":  ["sd"],           # Secure Development
    "CEK":  ["ck"],           # Cryptography, Encryption & Key Management
    "LOG":  ["lm"],           # Logging and Monitoring
    "A&A":  ["pm", "st"],     # Programme Management + Security Testing
    "DCS":  ["dc", "is"],     # Datacentre + Infrastructure Security
    "IPY":  ["is", "ns"],     # Infrastructure + Network
    "TVM":  ["is", "st"],     # Infrastructure Security + Security Testing
    "I&S":  ["ac"],           # Access Control
    "UEM":  ["is"],           # Infrastructure Security
}


class CcmHelper:
    """
    Helper for CSA CCM v4.1 compliance control lookups.

    Wraps the CTID-generated ccm_by_technique.yaml / ccm_by_control.yaml files
    with methods optimised for CloudPattern's threat-to-control lookup pattern.
    """

    def __init__(self, data_dir: Optional[Path] = None):
        self._dir = data_dir or _DATA_DIR
        self._by_technique: Dict[str, List[Dict]] = {}  # T#### → [{ccm_id, ...}]
        self._by_control: Dict[str, Dict] = {}           # ccm_id → {description, group, techniques}
        self._loaded = False
        self._load()

    def _load(self) -> None:
        tech_path = self._dir / "ccm_by_technique.yaml"
        ctrl_path = self._dir / "ccm_by_control.yaml"

        if not tech_path.exists():
            logger.warning(
                f"CCM technique index not found at {tech_path}. "
                "Run: python3 scripts/data/fetch_ccm.py"
            )
            return

        with open(tech_path, "r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        self._by_technique = data.get("data", {})

        if ctrl_path.exists():
            with open(ctrl_path, "r", encoding="utf-8") as fh:
                data2 = yaml.safe_load(fh)
            self._by_control = data2.get("data", {})

        self._loaded = True
        logger.info(
            f"CCM loaded: {len(self._by_technique)} technique entries, "
            f"{len(self._by_control)} CCM controls"
        )

    @property
    def is_loaded(self) -> bool:
        return self._loaded

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def get_controls_for_technique(self, technique_id: str) -> List[Dict]:
        """
        Return CCM controls that mitigate this MITRE T####.

        Each returned dict: {ccm_id, description, group, comments, ssrm_layer, ssp_prefixes}
        """
        entries = self._by_technique.get(technique_id, [])
        return [self._enrich(e) for e in entries]

    def get_controls_for_techniques(self, technique_ids: List[str]) -> List[Dict]:
        """
        Return deduplicated CCM controls across multiple MITRE T#### IDs.

        Controls that address more than one technique bubble up first
        (sorted by coverage count descending, then CCM ID ascending).
        """
        seen: Dict[str, Dict] = {}
        coverage: Dict[str, int] = {}

        for tid in technique_ids:
            for entry in self._by_technique.get(tid, []):
                cid = entry["ccm_id"]
                if cid not in seen:
                    seen[cid] = self._enrich(entry)
                    coverage[cid] = 0
                coverage[cid] += 1

        return sorted(
            seen.values(),
            key=lambda e: (-coverage[e["ccm_id"]], e["ccm_id"])
        )

    def get_control_info(self, ccm_id: str) -> Optional[Dict]:
        """Return full control record or None."""
        data = self._by_control.get(ccm_id)
        if not data:
            return None
        return {
            "ccm_id":      ccm_id,
            "description": data["description"],
            "group":       data["group"],
            "techniques":  data["techniques"],
            "ssrm_layer":  self.get_ssrm_layer(ccm_id),
            "ssp_prefixes": self.get_ssp_prefixes(ccm_id),
        }

    def get_ssrm_layer(self, ccm_id: str) -> str:
        """
        Return SSRM responsibility layer: 'shared', 'csc', or 'csp'.

        Heuristic based on CCM capability group — not formally encoded in CCM data.
        """
        group = self._group_for(ccm_id)
        return _SSRM_LAYER.get(group, "shared")

    def get_ssp_prefixes(self, ccm_id: str) -> List[str]:
        """
        Return SG SSP catalog category prefixes for this CCM control (best-effort).

        e.g. AIS-08 → ["as", "ac"]  (Application Security + Access Control)
        Callers can use these to filter cybersecurity_catalog.json for candidate controls.
        """
        group = self._group_for(ccm_id)
        return _CCM_TO_SSP_PREFIX.get(group, [])

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _group_for(self, ccm_id: str) -> str:
        """Extract capability group from control ID, e.g. 'IAM-16' → 'IAM'."""
        data = self._by_control.get(ccm_id)
        if data:
            return data.get("group", "")
        # Fallback: prefix before first '-'
        return ccm_id.split("-")[0] if "-" in ccm_id else ""

    def _enrich(self, entry: Dict) -> Dict:
        """Add ssrm_layer and ssp_prefixes to a raw by_technique entry."""
        cid = entry["ccm_id"]
        return {
            **entry,
            "ssrm_layer":   self.get_ssrm_layer(cid),
            "ssp_prefixes": self.get_ssp_prefixes(cid),
        }


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

_ccm_instance: Optional[CcmHelper] = None


def get_ccm_helper(data_dir: Optional[Path] = None) -> CcmHelper:
    """Return the shared CcmHelper singleton (lazy-loaded on first call)."""
    global _ccm_instance
    if _ccm_instance is None:
        _ccm_instance = CcmHelper(data_dir=data_dir)
    return _ccm_instance


__all__ = ["CcmHelper", "get_ccm_helper"]
