"""
mitre.py - MITRE ATT&CK integration scaffold

This module provides functions to query and use MITRE ATT&CK data for threat modeling and advisory.
"""

import json
import os
import logging

from chatbot.modules.pickle_cache import dump as _pkl_dump, load as _pkl_load

logger = logging.getLogger(__name__)


def _pickle_path(json_path: str) -> str:
    return json_path + ".pkl"


def _is_pickle_fresh(json_path: str, pkl_path: str) -> bool:
    """Return True if the signed pickle exists and is newer than the JSON source."""
    try:
        return (os.path.exists(pkl_path) and
                os.path.getmtime(pkl_path) > os.path.getmtime(json_path))
    except OSError:
        return False

# Module-level singleton — loaded once, shared across all callers
_instance = None

def get_mitre_helper(local_path=None):
    """Return the shared MitreHelper singleton, loading once on first call."""
    global _instance
    if _instance is None:
        _instance = MitreHelper(use_local=True, local_path=local_path)
    return _instance


class MitreHelper:
    def __init__(self, use_local=True, local_path=None):
        self.techniques = []
        self.tactics = []
        self.mitigations = []
        self.relationships = []
        self.data_objects = {}

        # O(1) lookup indexes built at load time
        self._technique_by_ext_id = {}   # "T1059" / "T1059.001" → technique obj
        self._technique_by_name  = {}    # lowercase name → technique obj
        self._mitigation_by_ext_id = {}  # "M1042" → mitigation obj
        self._mitigations_by_technique = {}  # technique internal_id → [mitigation dicts]

        if use_local:
            if not local_path:
                local_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'enterprise-attack.json')
            local_path = os.path.abspath(local_path)
            pkl_path = _pickle_path(local_path)
            try:
                if _is_pickle_fresh(local_path, pkl_path):
                    try:
                        self._load_from_pickle(pkl_path)
                        return
                    except ValueError as e:
                        # MAC failure or corrupt file — log and fall through to JSON
                        logger.warning(f"MITRE pickle cache rejected ({e}); reloading from JSON")
                self._load_from_json(local_path)
                self._save_pickle(pkl_path)
            except Exception as e:
                logger.error(f"Error loading local MITRE ATT&CK data: {e}")
        else:
            logger.warning("Online MITRE ATT&CK data loading not implemented yet.")

    def _load_from_pickle(self, pkl_path: str):
        """Load pre-built indexes from signed pickle (3× faster than JSON parse)."""
        state = _pkl_load(pkl_path)
        self.techniques                  = state['techniques']
        self.tactics                     = state['tactics']
        self.mitigations                 = state['mitigations']
        self.relationships               = state['relationships']
        self.data_objects                = state['data_objects']
        self._technique_by_ext_id        = state['_technique_by_ext_id']
        self._technique_by_name          = state['_technique_by_name']
        self._mitigation_by_ext_id       = state['_mitigation_by_ext_id']
        self._mitigations_by_technique   = state['_mitigations_by_technique']
        logger.info(
            f"MITRE cache loaded from pickle: {len(self.techniques)} techniques, "
            f"{len(self.tactics)} tactics"
        )

    def _load_from_json(self, local_path: str):
        """Parse enterprise-attack.json and build all indexes."""
        with open(local_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for obj in data.get('objects', []):
            obj_id   = obj.get('id')
            obj_type = obj.get('type')

            if obj_id:
                self.data_objects[obj_id] = obj

            if obj_type == 'attack-pattern':
                self.techniques.append(obj)
                for ref in obj.get('external_references', []):
                    ext_id = ref.get('external_id', '')
                    if ext_id:
                        self._technique_by_ext_id[ext_id.upper()] = obj
                name = obj.get('name', '')
                if name:
                    self._technique_by_name[name.lower()] = obj

            elif obj_type == 'x-mitre-tactic':
                self.tactics.append(obj)
            elif obj_type == 'course-of-action':
                self.mitigations.append(obj)
                for ref in obj.get('external_references', []):
                    ext_id = ref.get('external_id', '')
                    if ext_id and ext_id.startswith('M'):
                        self._mitigation_by_ext_id[ext_id.upper()] = obj
            elif obj_type == 'relationship':
                self.relationships.append(obj)

        for rel in self.relationships:
            if (rel.get('relationship_type') == 'mitigates'
                    and not rel.get('revoked', False)):
                target = rel.get('target_ref')
                if target:
                    self._mitigations_by_technique.setdefault(target, []).append(rel)

        logger.info(
            f"MITRE cache loaded from JSON: {len(self.techniques)} techniques, "
            f"{len(self.tactics)} tactics, {len(self.mitigations)} mitigations, "
            f"{len(self.relationships)} relationships"
        )

    def _save_pickle(self, pkl_path: str):
        """Persist parsed indexes as a signed pickle for faster subsequent loads."""
        try:
            state = {
                'techniques':                  self.techniques,
                'tactics':                     self.tactics,
                'mitigations':                 self.mitigations,
                'relationships':               self.relationships,
                'data_objects':                self.data_objects,
                '_technique_by_ext_id':        self._technique_by_ext_id,
                '_technique_by_name':          self._technique_by_name,
                '_mitigation_by_ext_id':       self._mitigation_by_ext_id,
                '_mitigations_by_technique':   self._mitigations_by_technique,
            }
            _pkl_dump(state, pkl_path)
            logger.info(f"MITRE signed pickle cache saved: {pkl_path}")
        except Exception as e:
            logger.warning(f"Could not save MITRE pickle cache: {e}")

    def get_techniques(self):
        return self.techniques

    def get_tactics(self):
        return self.tactics

    def get_mitigations(self):
        return self.mitigations

    def find_technique(self, name_or_id):
        # O(1) — check ext-id index first, then name index
        result = self._technique_by_ext_id.get(name_or_id.upper())
        if result:
            return result
        return self._technique_by_name.get(name_or_id.lower())

    def find_mitigation(self, mit_id):
        """Return mitigation object by external ID (e.g. 'M1042'). O(1)."""
        return self._mitigation_by_ext_id.get(mit_id.upper())

    def get_technique_summary(self, name_or_id):
        """Return a summary of a technique for bot advice."""
        tech = self.find_technique(name_or_id)
        if not tech:
            return f"Technique '{name_or_id}' not found."
        ext_refs = tech.get('external_references', [])
        ext_id = next((ref.get('external_id', '') for ref in ext_refs if 'external_id' in ref), 'N/A')
        summary = f"Technique: {tech.get('name', 'N/A')} (ID: {ext_id})\nDescription: {tech.get('description', 'No description available.')}"
        return summary

    def get_mitigation_advice(self, technique_id):
        """Return mitigation advice for a given technique ID."""
        mitigations = []
        for mit in self.mitigations:
            # Mitigations reference techniques via 'description' or 'external_references'
            if 'description' in mit and technique_id in mit['description']:
                mitigations.append(f"{mit.get('name', 'N/A')}: {mit.get('description', '')}")
        if not mitigations:
            return f"No mitigations found for technique {technique_id}."
        return "\n".join(mitigations)

    def get_tactic_by_name(self, name):
        """Return tactic details by name."""
        for tactic in self.tactics:
            if name.lower() in tactic.get('name', '').lower():
                return tactic
        return None

    def get_technique_mitigations(self, technique_id):
        """
        Get official MITRE mitigations for a technique.

        Args:
            technique_id: External ID (e.g., 'T1059.001') or internal ID (attack-pattern-xxx)

        Returns:
            List of dicts with mitigation details:
            [
                {
                    "mitigation_id": "M1042",
                    "mitigation_internal_id": "course-of-action--xxx",
                    "mitigation_name": "Disable or Remove Feature or Program",
                    "description": "General mitigation description...",
                    "specific_guidance": "How this mitigation applies to this technique...",
                    "url": "https://attack.mitre.org/mitigations/M1042"
                },
                ...
            ]
        """
        # Convert external ID to internal ID if needed
        if technique_id.startswith('T') or technique_id.startswith('AML'):
            tech = self.find_technique(technique_id)
            if not tech:
                return []
            technique_internal_id = tech.get('id')
        else:
            technique_internal_id = technique_id

        # O(1) — use pre-built relationships index
        mitigation_relationships = self._mitigations_by_technique.get(technique_internal_id, [])

        # Build mitigation details
        mitigations = []

        for rel in mitigation_relationships:
            mitigation_internal_id = rel.get('source_ref')

            # Get mitigation object
            mitigation = self.data_objects.get(mitigation_internal_id)

            if not mitigation:
                continue

            # Extract external ID (e.g., M1042)
            ext_refs = mitigation.get('external_references', [])
            mitigation_ext_id = next(
                (ref.get('external_id') for ref in ext_refs if 'external_id' in ref),
                'Unknown'
            )

            # Get URL
            url = next(
                (ref.get('url') for ref in ext_refs if ref.get('source_name') == 'mitre-attack'),
                f"https://attack.mitre.org/mitigations/{mitigation_ext_id}"
            )

            mitigations.append({
                "mitigation_id": mitigation_ext_id,
                "mitigation_internal_id": mitigation_internal_id,
                "mitigation_name": mitigation.get('name', 'Unknown'),
                "description": mitigation.get('description', ''),
                "specific_guidance": rel.get('description', ''),  # Relationship description
                "url": url
            })

        return mitigations

    def get_mitigations_for_techniques(self, technique_ids):
        """
        Get mitigations for multiple techniques with deduplication.

        Args:
            technique_ids: List of technique IDs (external or internal)

        Returns:
            List of deduplicated mitigation dicts with addresses_techniques field:
            [
                {
                    "mitigation_id": "M1042",
                    "mitigation_name": "...",
                    "description": "...",
                    "addresses_techniques": ["T1059.001", "T1053.005"],
                    "specific_guidance": {
                        "T1059.001": "How it applies to PowerShell...",
                        "T1053.005": "How it applies to Scheduled Task..."
                    },
                    "url": "..."
                },
                ...
            ]
        """
        # Collect all mitigations with technique mapping
        mitigation_map = {}  # mitigation_id -> mitigation data

        for tech_id in technique_ids:
            tech_mitigations = self.get_technique_mitigations(tech_id)

            for mit in tech_mitigations:
                mit_id = mit['mitigation_id']

                if mit_id not in mitigation_map:
                    # First time seeing this mitigation
                    mitigation_map[mit_id] = {
                        "mitigation_id": mit_id,
                        "mitigation_internal_id": mit['mitigation_internal_id'],
                        "mitigation_name": mit['mitigation_name'],
                        "description": mit['description'],
                        "addresses_techniques": [],
                        "specific_guidance": {},
                        "url": mit['url']
                    }

                # Add technique to addresses list
                # Convert to external ID if needed
                if tech_id.startswith('attack-pattern'):
                    tech = self.data_objects.get(tech_id)
                    if tech:
                        ext_refs = tech.get('external_references', [])
                        tech_ext_id = next(
                            (ref.get('external_id') for ref in ext_refs if 'external_id' in ref),
                            tech_id
                        )
                    else:
                        tech_ext_id = tech_id
                else:
                    tech_ext_id = tech_id

                if tech_ext_id not in mitigation_map[mit_id]['addresses_techniques']:
                    mitigation_map[mit_id]['addresses_techniques'].append(tech_ext_id)

                # Store specific guidance for this technique
                mitigation_map[mit_id]['specific_guidance'][tech_ext_id] = mit['specific_guidance']

        # Return as list sorted by number of techniques addressed (ROI)
        mitigations_list = list(mitigation_map.values())
        mitigations_list.sort(key=lambda m: len(m['addresses_techniques']), reverse=True)

        return mitigations_list
