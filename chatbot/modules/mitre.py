"""
mitre.py - MITRE ATT&CK integration scaffold

This module provides functions to query and use MITRE ATT&CK data for threat modeling and advisory.
"""

# You need to install mitreattack-python:
# pip install mitreattack-python

import json
import os

class MitreHelper:
    def __init__(self, use_local=True, local_path=None):
        self.techniques = []
        self.tactics = []
        self.mitigations = []
        if use_local:
            # Default path for local enterprise-attack.json
            if not local_path:
                local_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'enterprise-attack.json')
            try:
                with open(local_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                for obj in data.get('objects', []):
                    if obj.get('type') == 'attack-pattern':
                        self.techniques.append(obj)
                    elif obj.get('type') == 'x-mitre-tactic':
                        self.tactics.append(obj)
                    elif obj.get('type') == 'course-of-action':
                        self.mitigations.append(obj)
            except Exception as e:
                print(f"Error loading local MITRE ATT&CK data: {e}")
        else:
            # Future: Add online data loading here
            print("Online MITRE ATT&CK data loading not implemented yet.")

    def get_techniques(self):
        return self.techniques

    def get_tactics(self):
        return self.tactics

    def get_mitigations(self):
        return self.mitigations

    def find_technique(self, name_or_id):
        for tech in self.techniques:
            ext_refs = tech.get('external_references', [])
            ext_id = next((ref.get('external_id', '') for ref in ext_refs if 'external_id' in ref), '')
            # Match external_id or name exactly
            if name_or_id.lower() == ext_id.lower() or name_or_id.lower() == tech.get('name', '').lower():
                return tech
        return None

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
