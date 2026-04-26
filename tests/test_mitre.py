"""
test_mitre.py - Unit tests for mitre.py MITRE ATT&CK integration
"""
import unittest
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from chatbot.modules.mitre import MitreHelper

class TestMitreHelper(unittest.TestCase):
    def setUp(self):
        self.mitre = MitreHelper(use_local=True)

    def test_get_techniques(self):
        techniques = self.mitre.get_techniques()
        self.assertIsInstance(techniques, list)
        self.assertTrue(len(techniques) > 0, "No techniques loaded from local JSON.")

    def test_get_tactics(self):
        tactics = self.mitre.get_tactics()
        self.assertIsInstance(tactics, list)
        self.assertTrue(len(tactics) > 0, "No tactics loaded from local JSON.")

    def test_get_mitigations(self):
        mitigations = self.mitre.get_mitigations()
        self.assertIsInstance(mitigations, list)
        self.assertTrue(len(mitigations) > 0, "No mitigations loaded from local JSON.")

    def test_find_technique_by_id(self):
        tech = self.mitre.find_technique("T1059")
        self.assertIsNotNone(tech, "Technique T1059 not found.")
        self.assertIn("Command and Scripting Interpreter", tech.get("name", ""))

    def test_get_technique_summary(self):
        summary = self.mitre.get_technique_summary("T1059")
        self.assertIn("Command and Scripting Interpreter", summary)
        self.assertIn("T1059", summary)

    def test_list_tactic_names(self):
        tactics = self.mitre.get_tactics()
        names = [t.get('name', '') for t in tactics]
        self.assertIn("Execution", names)

    def test_get_tactic_by_name(self):
        tactic = self.mitre.get_tactic_by_name("Execution")
        self.assertIsNotNone(tactic)
        self.assertIn("Execution", tactic.get("name", ""))

    def test_get_mitigation_advice(self):
        advice = self.mitre.get_mitigation_advice("T1059")
        self.assertIsInstance(advice, str)
        # Advice may be empty if no direct mitigations, but should not error

if __name__ == "__main__":
    unittest.main()
