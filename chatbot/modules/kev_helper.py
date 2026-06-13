"""
kev_helper.py - CISA KEV + CTID KEV→ATT&CK lookup helper.

Two data sources:
  kev_ctid_by_technique.json  — CVEs mapped to ATT&CK T-codes (CTID, Apache 2.0)
  kev_cisa_by_cve.json        — Actively exploited CVE metadata with ransomware flags (CISA)

Use get_kev_helper() for the module-level singleton.
Gracefully returns empty results if data files are missing (non-blocking).
"""

import json
import logging
import os
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

_DATA_DIR = os.path.join(os.path.dirname(__file__), '..', 'data', 'kev')
_CTID_PATH = os.path.join(_DATA_DIR, 'kev_ctid_by_technique.json')
_CISA_PATH = os.path.join(_DATA_DIR, 'kev_cisa_by_cve.json')

_instance = None


def get_kev_helper() -> "KevHelper":
    """Return the shared KevHelper singleton, loading once on first call."""
    global _instance
    if _instance is None:
        _instance = KevHelper()
    return _instance


class KevHelper:
    def __init__(self):
        self._ctid_by_technique: Dict[str, List[Dict]] = {}  # T1190 → [{cve_id, ...}]
        self._cisa_by_cve: Dict[str, Dict] = {}              # CVE-2021-44228 → {vendor, ...}
        self._available = False
        self._load()

    def _load(self) -> None:
        ctid_path = os.path.abspath(_CTID_PATH)
        cisa_path = os.path.abspath(_CISA_PATH)

        if not os.path.exists(ctid_path) or not os.path.exists(cisa_path):
            logger.warning(
                "KEV data files not found — run 'python3 scripts/data/fetch_kev.py' to download. "
                "CVE enrichment will be skipped."
            )
            return

        try:
            ctid_raw = json.loads(open(ctid_path, encoding='utf-8').read())
            self._ctid_by_technique = ctid_raw.get('data', {})

            cisa_raw = json.loads(open(cisa_path, encoding='utf-8').read())
            self._cisa_by_cve = cisa_raw.get('data', {})

            self._available = True
            logger.info(
                f"KEV loaded: {len(self._ctid_by_technique)} techniques (CTID), "
                f"{len(self._cisa_by_cve)} CVEs (CISA)"
            )
        except Exception as e:
            logger.warning(f"KEV load failed: {e} — CVE enrichment will be skipped.")

    @property
    def available(self) -> bool:
        return self._available

    def get_cves_for_technique(self, technique_id: str) -> List[Dict]:
        """
        Return CVEs mapped to a technique by CTID, enriched with CISA metadata.
        technique_id: external ATT&CK ID, e.g. 'T1190'.

        Returns list of dicts:
          {cve_id, mapping_types, capability_group, cve_description,
           actively_exploited, ransomware, vendor, product, date_added, cwes}
        """
        if not self._available:
            return []

        ctid_entries = self._ctid_by_technique.get(technique_id.upper(), [])
        result = []
        for entry in ctid_entries:
            cve_id = entry['cve_id'].upper()
            cisa = self._cisa_by_cve.get(cve_id, {})
            result.append({
                'cve_id':           cve_id,
                'mapping_types':    entry.get('mapping_types', []),
                'capability_group': entry.get('capability_group', ''),
                'cve_description':  entry.get('cve_description', ''),
                'actively_exploited': bool(cisa),
                'ransomware':       cisa.get('ransomware', False),
                'vendor':           cisa.get('vendor', ''),
                'product':          cisa.get('product', ''),
                'date_added':       cisa.get('date_added', ''),
                'cwes':             cisa.get('cwes', []),
            })
        return result

    def get_entry(self, cve_id: str) -> Optional[Dict]:
        """Return CISA KEV entry for a CVE ID, or None if not actively exploited."""
        return self._cisa_by_cve.get(cve_id.upper())

    def is_actively_exploited(self, cve_id: str) -> bool:
        """True if the CVE appears in the CISA KEV catalog."""
        return cve_id.upper() in self._cisa_by_cve

    def has_ransomware_use(self, cve_id: str) -> bool:
        """True if CISA flags this CVE as used in known ransomware campaigns."""
        entry = self._cisa_by_cve.get(cve_id.upper(), {})
        return entry.get('ransomware', False)
