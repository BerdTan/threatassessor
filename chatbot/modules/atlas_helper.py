"""
MITRE ATLAS Helper - AI/ML Threat Framework

Provides access to MITRE ATLAS (Adversarial Threat Landscape for AI Systems):
- 51+ techniques across 13 tactics
- 46+ mitigations for ML-specific threats
- Case studies of real-world AI attacks

ATLAS complements ARC Framework:
- ARC: Risk categories (Integrity, Safety, Security, Privacy, etc.)
- ATLAS: Attack techniques (Poisoning, Evasion, Model Inversion, etc.)

Data source: https://github.com/mitre-atlas/atlas-data
Version: 2025-04-09

Usage:
    atlas = AtlasHelper()
    techniques = atlas.get_techniques()
    mitigations = atlas.get_mitigations()
    technique_info = atlas.get_technique_by_id("AML.T0043")
"""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Set
import yaml

logger = logging.getLogger(__name__)


class AtlasHelper:
    """
    Helper for MITRE ATLAS (AI/ML threat framework).

    Loads and provides access to:
    - Techniques: Attack techniques for ML systems (AML.T####)
    - Mitigations: Defenses against ML attacks (AML.M####)
    - Tactics: Attack stages (Reconnaissance, Resource Development, etc.)
    """

    def __init__(self, data_dir: Optional[str] = None):
        """
        Initialize ATLAS helper.

        Args:
            data_dir: Path to ATLAS data directory (default: chatbot/data/atlas/)
        """
        if data_dir is None:
            # Default to chatbot/data/atlas/
            module_dir = Path(__file__).parent.parent
            data_dir = module_dir / "data" / "atlas"

        self.data_dir = Path(data_dir)
        self.techniques: Dict[str, Dict] = {}
        self.mitigations: Dict[str, Dict] = {}
        self.tactics: Dict[str, Dict] = {}

        self._load_data()

    def _load_data(self):
        """Load ATLAS data from YAML files."""
        try:
            # Load techniques
            techniques_path = self.data_dir / "techniques.yaml"
            if techniques_path.exists():
                with open(techniques_path, 'r', encoding='utf-8') as f:
                    techniques_data = yaml.safe_load(f)
                    if techniques_data:
                        for tech in techniques_data:
                            if 'id' in tech:
                                self.techniques[tech['id']] = tech

                logger.info(f"Loaded {len(self.techniques)} ATLAS techniques")

            # Load mitigations
            mitigations_path = self.data_dir / "mitigations.yaml"
            if mitigations_path.exists():
                with open(mitigations_path, 'r', encoding='utf-8') as f:
                    mitigations_data = yaml.safe_load(f)
                    if mitigations_data:
                        for mit in mitigations_data:
                            if 'id' in mit:
                                self.mitigations[mit['id']] = mit

                logger.info(f"Loaded {len(self.mitigations)} ATLAS mitigations")

            # Load tactics
            tactics_path = self.data_dir / "tactics.yaml"
            if tactics_path.exists():
                with open(tactics_path, 'r', encoding='utf-8') as f:
                    tactics_data = yaml.safe_load(f)
                    if tactics_data:
                        for tac in tactics_data:
                            if 'id' in tac:
                                self.tactics[tac['id']] = tac

                logger.info(f"Loaded {len(self.tactics)} ATLAS tactics")

        except Exception as e:
            logger.warning(f"Failed to load ATLAS data: {e}")

    def get_techniques(self) -> Dict[str, Dict]:
        """
        Get all ATLAS techniques.

        Returns:
            Dict mapping technique ID (AML.T####) to technique data
        """
        return self.techniques

    def get_mitigations(self) -> Dict[str, Dict]:
        """
        Get all ATLAS mitigations.

        Returns:
            Dict mapping mitigation ID (AML.M####) to mitigation data
        """
        return self.mitigations

    def get_tactics(self) -> Dict[str, Dict]:
        """
        Get all ATLAS tactics.

        Returns:
            Dict mapping tactic ID to tactic data
        """
        return self.tactics

    def get_technique_by_id(self, technique_id: str) -> Optional[Dict]:
        """
        Get technique by ID.

        Args:
            technique_id: Technique ID (e.g., "AML.T0043")

        Returns:
            Technique data or None if not found
        """
        return self.techniques.get(technique_id)

    def get_mitigation_by_id(self, mitigation_id: str) -> Optional[Dict]:
        """
        Get mitigation by ID.

        Args:
            mitigation_id: Mitigation ID (e.g., "AML.M0000")

        Returns:
            Mitigation data or None if not found
        """
        return self.mitigations.get(mitigation_id)

    def get_techniques_for_tactic(self, tactic_id: str) -> List[Dict]:
        """
        Get all techniques for a tactic.

        Args:
            tactic_id: Tactic ID (e.g., "AML.TA0001")

        Returns:
            List of techniques for this tactic
        """
        techniques = []
        for tech in self.techniques.values():
            if 'tactics' in tech and tactic_id in tech['tactics']:
                techniques.append(tech)
        return techniques

    def get_mitigations_for_technique(self, technique_id: str) -> List[Dict]:
        """
        Get mitigations that address a technique.

        Args:
            technique_id: Technique ID (e.g., "AML.T0043")

        Returns:
            List of mitigations for this technique
        """
        mitigations = []
        for mit in self.mitigations.values():
            if 'techniques' in mit:
                for tech_ref in mit['techniques']:
                    if isinstance(tech_ref, dict) and tech_ref.get('id') == technique_id:
                        mitigations.append(mit)
                        break
        return mitigations

    def get_techniques_by_component(self, component_type: str) -> List[str]:
        """
        Get ATLAS techniques relevant to an AI component type.

        Maps AI component types to relevant ATLAS techniques.

        Args:
            component_type: AI component type (llm_api, vector_db, agent_orchestrator, etc.)

        Returns:
            List of technique IDs
        """
        # Map component types to ATLAS techniques
        component_techniques = {
            "llm_api": [
                "AML.T0051",     # LLM Prompt Injection
                "AML.T0051.000", # Direct Prompt Injection
                "AML.T0051.001", # Indirect Prompt Injection
                "AML.T0054",     # LLM Jailbreak
                "AML.T0048",     # Exfiltration via Model Output
                "AML.T0043",     # Model Inversion
            ],
            "vector_db": [
                "AML.T0020",     # Poison Training Data
                "AML.T0018",     # Backdoor ML Model
                "AML.T0025",     # Exfiltration via Cyber Means
                "AML.T0024",     # Exfiltration via ML Model
            ],
            "agent_orchestrator": [
                "AML.T0051",     # LLM Prompt Injection
                "AML.T0054",     # LLM Jailbreak
                "AML.T0044",     # Full ML Model Access
                "AML.T0040",     # ML Model Inference API Access
            ],
            "embedding_service": [
                "AML.T0043",     # Model Inversion
                "AML.T0048",     # Exfiltration via Model Output
            ],
            "code_execution": [
                "AML.T0051.001", # Indirect Prompt Injection
                "AML.T0054",     # LLM Jailbreak
                "AML.T0048",     # Exfiltration via Model Output
            ],
            "prompt_manager": [
                "AML.T0051",     # LLM Prompt Injection
                "AML.T0051.000", # Direct Prompt Injection
                "AML.T0051.001", # Indirect Prompt Injection
            ],
            "tool_registry": [
                "AML.T0044",     # Full ML Model Access
                "AML.T0040",     # ML Model Inference API Access
            ]
        }

        return component_techniques.get(component_type, [])

    def get_technique_name(self, technique_id: str) -> str:
        """
        Get technique name from ID.

        Args:
            technique_id: Technique ID (e.g., "AML.T0043")

        Returns:
            Technique name or ID if not found
        """
        tech = self.techniques.get(technique_id)
        if tech and 'name' in tech:
            return tech['name']
        return technique_id

    def search_techniques(self, query: str) -> List[Dict]:
        """
        Search techniques by keyword.

        Args:
            query: Search query (case-insensitive)

        Returns:
            List of matching techniques
        """
        query_lower = query.lower()
        results = []

        for tech in self.techniques.values():
            if (query_lower in tech.get('name', '').lower() or
                query_lower in tech.get('description', '').lower()):
                results.append(tech)

        return results


__all__ = ['AtlasHelper']
