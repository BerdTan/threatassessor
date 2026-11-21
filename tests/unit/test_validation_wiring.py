"""Two analysis-time validation bugs seen in a live run (2026-11-21), both swallowed by
warn-and-continue handlers so no test or metric ever noticed."""
import ast
import inspect

from chatbot.modules import completeness_validator as cv


def test_every_validation_issue_supplies_impact():
    tree = ast.parse(inspect.getsource(cv))
    bad = [n.lineno for n in ast.walk(tree)
           if isinstance(n, ast.Call) and getattr(n.func, "id", "") == "ValidationIssue"
           and len(n.args) < 4 and "impact" not in {k.arg for k in n.keywords}]
    assert not bad, f"ValidationIssue without impact at lines {bad}"


def test_service_validates_the_ground_truth_dict_not_the_name():
    from chatbot.services.threat_analysis_service import ThreatAnalysisService
    src = inspect.getsource(ThreatAnalysisService)
    assert "validate_completeness(arch_name)" not in src


def test_validator_accepts_a_ground_truth_dict():
    r = cv.validate_completeness({"metadata": {}, "attack_paths": [], "mitigations": []})
    assert isinstance(r, dict)
