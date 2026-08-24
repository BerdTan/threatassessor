"""
Tests for incident-simulator: scenario payloads fire expected DETECT rules.

Covers:
  - All 5 scenarios fire their documented expected rules
  - No scenario fires false positives on a clean baseline
  - DETECT-002/007 mutual exclusion (divergence_detected flag)
  - Storycaster prompt structure (no LLM call — tests prompt content only)
  - write_to_report merges signals without destroying existing governance data

No LLM calls, no network, no filesystem writes to report/.
Expected runtime: < 2 seconds.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Dict, Set

import pytest

# ---------------------------------------------------------------------------
# Import simulator script
# ---------------------------------------------------------------------------

_SCRIPT = (
    Path(__file__).parents[1]
    / ".claude/skills/incident-simulator/scripts/incident_simulator.py"
)

spec = importlib.util.spec_from_file_location("incident_simulator", _SCRIPT)
_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(_mod)

SCENARIOS        = _mod.SCENARIOS
EXPECTED_RULES   = _mod.EXPECTED_RULES
_evaluate        = _mod._evaluate
_build_story_prompt = _mod._build_story_prompt


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _fired_ids(signals: Dict) -> Set[str]:
    findings = _evaluate(signals)
    return {f["unmapped"]["rule_id"] for f in findings if f.get("unmapped", {}).get("rule_id")}


# ---------------------------------------------------------------------------
# All scenarios fire expected rules
# ---------------------------------------------------------------------------

class TestScenariosFire:
    def test_targeted_pipeline_attack(self):
        fn, _ = SCENARIOS["targeted_pipeline_attack"]
        fired = _fired_ids(fn())
        assert {"DETECT-005", "DETECT-002"} <= fired

    def test_rationalize_and_escape(self):
        fn, _ = SCENARIOS["rationalize_and_escape"]
        fired = _fired_ids(fn())
        assert {"DETECT-001", "DETECT-003", "DETECT-007"} <= fired

    def test_exfil_with_adversarial(self):
        fn, _ = SCENARIOS["exfil_with_adversarial"]
        fired = _fired_ids(fn())
        assert {"DETECT-005", "DETECT-004"} <= fired

    def test_swarm_with_hyperfocus(self):
        fn, _ = SCENARIOS["swarm_with_hyperfocus"]
        fired = _fired_ids(fn())
        assert {"DETECT-006", "DETECT-003"} <= fired

    def test_full_compromise(self):
        fn, _ = SCENARIOS["full_compromise"]
        fired = _fired_ids(fn())
        assert {"DETECT-001", "DETECT-002", "DETECT-004", "DETECT-005"} <= fired

    # ── New scenarios (DETECT-008 through DETECT-015) ──────────────────────

    def test_credential_leak_in_architecture(self):
        fn, _ = SCENARIOS["credential_leak_in_architecture"]
        fired = _fired_ids(fn())
        assert {"DETECT-009"} <= fired

    def test_path_traversal_mmd_probe(self):
        fn, _ = SCENARIOS["path_traversal_mmd_probe"]
        fired = _fired_ids(fn())
        assert {"DETECT-010"} <= fired

    def test_llm_egress_no_zdr(self):
        fn, _ = SCENARIOS["llm_egress_no_zdr"]
        fired = _fired_ids(fn())
        assert {"DETECT-011"} <= fired

    def test_stale_mitre_data(self):
        fn, _ = SCENARIOS["stale_mitre_data"]
        fired = _fired_ids(fn())
        assert {"DETECT-012"} <= fired

    def test_high_outbound_surface(self):
        fn, _ = SCENARIOS["high_outbound_surface"]
        fired = _fired_ids(fn())
        assert {"DETECT-013"} <= fired

    def test_sm_selection_pressure(self):
        fn, _ = SCENARIOS["sm_selection_pressure"]
        fired = _fired_ids(fn())
        assert {"DETECT-008"} <= fired

    def test_low_validation_coverage(self):
        fn, _ = SCENARIOS["low_validation_coverage"]
        fired = _fired_ids(fn())
        assert {"DETECT-014"} <= fired

    def test_critic_convergence(self):
        fn, _ = SCENARIOS["critic_convergence"]
        fired = _fired_ids(fn())
        assert {"DETECT-015"} <= fired

    def test_supply_chain_and_credentials(self):
        fn, _ = SCENARIOS["supply_chain_and_credentials"]
        fired = _fired_ids(fn())
        assert {"DETECT-009", "DETECT-012"} <= fired

    def test_egress_and_low_validation(self):
        fn, _ = SCENARIOS["egress_and_low_validation"]
        fired = _fired_ids(fn())
        assert {"DETECT-011", "DETECT-014", "DETECT-015"} <= fired

    # ── AST-grounded scenarios (DETECT-016/017/018) ────────────────────────

    def test_critic_module_tampered(self):
        fn, _ = SCENARIOS["critic_module_tampered"]
        fired = _fired_ids(fn())
        assert {"DETECT-016"} <= fired

    def test_mutable_url_in_mmd(self):
        fn, _ = SCENARIOS["mutable_url_in_mmd"]
        fired = _fired_ids(fn())
        assert {"DETECT-017"} <= fired

    def test_homoglyph_evasion_attempt(self):
        fn, _ = SCENARIOS["homoglyph_evasion_attempt"]
        fired = _fired_ids(fn())
        assert {"DETECT-018"} <= fired

    def test_ast_composite(self):
        fn, _ = SCENARIOS["ast_composite"]
        fired = _fired_ids(fn())
        assert {"DETECT-016", "DETECT-017", "DETECT-018"} <= fired

    def test_high_category_injection(self):
        fn, _ = SCENARIOS["high_category_injection"]
        fired = _fired_ids(fn())
        assert {"DETECT-019"} <= fired

    def test_rest_rate_limit_abuse(self):
        fn, _ = SCENARIOS["rest_rate_limit_abuse"]
        fired = _fired_ids(fn())
        assert {"DETECT-032"} <= fired

    def test_arch_name_path_traversal(self):
        fn, _ = SCENARIOS["arch_name_path_traversal"]
        fired = _fired_ids(fn())
        assert {"DETECT-033"} <= fired

    def test_all_expected_rules_match_documented(self):
        """Every scenario fires at least its documented expected set."""
        for name, (fn, _) in SCENARIOS.items():
            fired  = _fired_ids(fn())
            expect = EXPECTED_RULES.get(name, set())
            missing = expect - fired
            assert not missing, f"{name}: expected {missing} to fire but didn't"


# ---------------------------------------------------------------------------
# Clean baseline fires nothing
# ---------------------------------------------------------------------------

class TestNoFalsePositives:
    def test_clean_base_fires_no_rules(self):
        fired = _fired_ids(_mod._base())
        assert fired == set(), f"False positives on clean baseline: {fired}"


# ---------------------------------------------------------------------------
# DETECT-002 / DETECT-007 mutual exclusion
# ---------------------------------------------------------------------------

class TestMutualExclusion:
    def test_detect007_requires_divergence_false(self):
        """DETECT-007 fires only when divergence_detected=False."""
        fn, _ = SCENARIOS["rationalize_and_escape"]
        sig = fn()
        # rationalize_and_escape has divergence_detected=False → DETECT-007 fires
        assert "DETECT-007" in _fired_ids(sig)
        assert "DETECT-002" not in _fired_ids(sig)

    def test_detect002_requires_divergence_true(self):
        """DETECT-002 fires only when divergence_detected=True."""
        fn, _ = SCENARIOS["targeted_pipeline_attack"]
        sig = fn()
        # targeted_pipeline_attack has divergence_detected=True → DETECT-002 fires
        assert "DETECT-002" in _fired_ids(sig)
        assert "DETECT-007" not in _fired_ids(sig)

    def test_full_compromise_fires_detect002_not_007(self):
        fn, _ = SCENARIOS["full_compromise"]
        sig = fn()
        fired = _fired_ids(sig)
        assert "DETECT-002" in fired
        assert "DETECT-007" not in fired


# ---------------------------------------------------------------------------
# Scenario severity ordering (highest first when sorted)
# ---------------------------------------------------------------------------

class TestSeverityOrdering:
    def test_targeted_pipeline_has_critical_rules(self):
        fn, _ = SCENARIOS["targeted_pipeline_attack"]
        fired = _evaluate(fn())
        sevs = {f["severity"] for f in fired if f.get("unmapped", {}).get("rule_id")}
        assert "Critical" in sevs

    def test_swarm_scenario_has_no_critical_rules(self):
        fn, _ = SCENARIOS["swarm_with_hyperfocus"]
        fired = _evaluate(fn())
        sevs = {f["severity"] for f in fired if f.get("unmapped", {}).get("rule_id")}
        assert "Critical" not in sevs
        assert "High" in sevs or "Medium" in sevs

    def test_full_compromise_highest_severity_is_critical(self):
        fn, _ = SCENARIOS["full_compromise"]
        fired = _evaluate(fn())
        sev_ord = {"Critical": 4, "High": 3, "Medium": 2, "Low": 1}
        rule_findings = [f for f in fired if f.get("unmapped", {}).get("rule_id")]
        worst = max(rule_findings, key=lambda f: sev_ord.get(f["severity"], 0))
        assert worst["severity"] == "Critical"


# ---------------------------------------------------------------------------
# Multi-rule co-occurrence: each scenario fires >= documented count
# ---------------------------------------------------------------------------

class TestMultiRuleFires:
    def test_rationalize_fires_3_rules(self):
        fn, _ = SCENARIOS["rationalize_and_escape"]
        fired = _fired_ids(fn())
        assert len(fired) >= 3

    def test_full_compromise_fires_4_rules(self):
        fn, _ = SCENARIOS["full_compromise"]
        fired = _fired_ids(fn())
        assert len(fired) >= 4

    def test_exfil_fires_both_kill_chains(self):
        """exfil scenario fires one initial_access rule and one exfiltration rule."""
        fn, _ = SCENARIOS["exfil_with_adversarial"]
        fired_findings = [f for f in _evaluate(fn()) if f.get("unmapped", {}).get("rule_id")]
        kill_chains = {f["unmapped"]["kill_chain_stage"] for f in fired_findings}
        assert "initial_access" in kill_chains
        assert "exfiltration" in kill_chains


# ---------------------------------------------------------------------------
# Storycaster prompt (no LLM — validates prompt content and structure)
# ---------------------------------------------------------------------------

class TestStorycasterPrompt:
    def _make_finding(self, rule_id="DETECT-005", severity="Critical"):
        return {
            "class_uid": 2004,
            "severity": severity,
            "finding": {"title": f"{rule_id} Alert", "desc": "test desc"},
            "unmapped": {
                "rule_id": rule_id,
                "kill_chain_stage": "initial_access",
                "incident_refs": ["huggingface-dataset-pipeline-2026"],
                "playbook_steps": ["Step 1: quarantine", "Step 2: forensics"],
            },
        }

    def test_prompt_contains_scenario_desc(self):
        fn, desc = SCENARIOS["targeted_pipeline_attack"]
        findings = [self._make_finding()]
        arch_ctx = {"description": "Web app with ALB", "user_stories": {"edges": []}}
        prompt = _build_story_prompt("targeted_pipeline_attack", fn(), findings,
                                     "03_aws_3tier", arch_ctx)
        assert "targeted_pipeline_attack" in prompt or "DETECT-005" in prompt

    def test_prompt_contains_arch_description(self):
        fn, _ = SCENARIOS["exfil_with_adversarial"]
        findings = [self._make_finding()]
        arch_ctx = {"description": "Three-tier AWS architecture", "user_stories": {"edges": []}}
        prompt = _build_story_prompt("exfil_with_adversarial", fn(), findings,
                                     "03_aws_3tier", arch_ctx)
        assert "Three-tier AWS architecture" in prompt

    def test_prompt_contains_playbook_steps(self):
        fn, _ = SCENARIOS["targeted_pipeline_attack"]
        findings = [self._make_finding()]
        arch_ctx = {"description": "Test arch", "user_stories": {"edges": []}}
        prompt = _build_story_prompt("targeted_pipeline_attack", fn(), findings,
                                     "test_arch", arch_ctx)
        assert "quarantine" in prompt.lower() or "forensics" in prompt.lower()

    def test_prompt_requests_three_sections(self):
        fn, _ = SCENARIOS["full_compromise"]
        fn2, _ = SCENARIOS["full_compromise"]
        all_fired = _evaluate(fn2())
        arch_ctx = {"description": "Complex enterprise", "user_stories": {"edges": []}}
        prompt = _build_story_prompt("full_compromise", fn(), all_fired,
                                     "10_complex_enterprise", arch_ctx)
        assert "What Happened" in prompt
        assert "How We Detected" in prompt
        assert "What To Do" in prompt

    def test_prompt_instructs_no_field_names(self):
        """Prompt must instruct the LLM not to output governance field names."""
        fn, _ = SCENARIOS["rationalize_and_escape"]
        fired = _evaluate(fn())
        arch_ctx = {"description": "Test", "user_stories": {"edges": []}}
        prompt = _build_story_prompt("rationalize_and_escape", fn(), fired,
                                     "03_aws_3tier", arch_ctx)
        # Prompt explicitly instructs LLM not to use field names
        assert "Do not use field names" in prompt or "field names" in prompt


# ---------------------------------------------------------------------------
# write_to_report merges without destroying existing data
# ---------------------------------------------------------------------------

class TestWriteToReport:
    def test_write_merges_with_existing(self, tmp_path):
        arch_dir = tmp_path / "test_arch"
        arch_dir.mkdir()
        existing = {"existing_key": "keep_me", "manipulation": {"severity": "LOW"}}
        (arch_dir / "governance_signals.json").write_text(json.dumps(existing))

        fn, _ = SCENARIOS["targeted_pipeline_attack"]
        signals = fn()

        # Patch REPORT_DIR
        orig = _mod.REPORT_DIR
        _mod.REPORT_DIR = tmp_path
        try:
            out = _mod.write_to_report("targeted_pipeline_attack", signals, "test_arch")
        finally:
            _mod.REPORT_DIR = orig

        result = json.loads(out.read_text())
        assert result["existing_key"] == "keep_me"
        assert result["exploitation"]["severity"] == "CRITICAL"

    def test_write_creates_dir_if_missing(self, tmp_path):
        fn, _ = SCENARIOS["swarm_with_hyperfocus"]
        orig = _mod.REPORT_DIR
        _mod.REPORT_DIR = tmp_path
        try:
            out = _mod.write_to_report("swarm_with_hyperfocus", fn(), "new_arch")
        finally:
            _mod.REPORT_DIR = orig
        assert out.exists()
        data = json.loads(out.read_text())
        assert data["aivss"]["coverage_pct"] == 72
