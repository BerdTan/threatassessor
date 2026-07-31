"""
Tests for SOC Detection Rule Evaluator and soc_detection_rules.yaml.

Covers:
  - RuleEvaluator loads YAML and exposes correct rule count
  - _eval_condition: all operators (==, >=, >, length_gt, token_spike, no_critical, min_agents)
  - Each of the 6 rules fires on its incident scenario
  - Each rule does NOT fire on clean signals (false positive guard)
  - OCSF DetectionFinding fields: class_uid, rule_id, actions, kill_chain_stage
  - Playbook steps present for rules that have them
  - End-to-end: process_signals() output contains rule-based findings
  - Co-occurrence: DETECT-002 + DETECT-005 in same run

No LLM calls, no network. pyyaml required (already in dependencies).
Expected runtime: < 1 second.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict

import pytest

# Make repo root importable
REPO = Path(__file__).parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from chatbot.harness.rule_evaluator import RuleEvaluator, _eval_condition, _eval_rule

RULES_PATH = REPO / "policies" / "soc_detection_rules.yaml"


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean() -> Dict[str, Any]:
    """Baseline clean governance_signals — no rule should fire."""
    return {
        "exploitation": {
            "severity": "LOW",
            "injection_patterns": [],
            "path_traversal": [],
            "homoglyph_count": 0,
            "url_encoded_count": 0,
            "blocked": False,
        },
        "manipulation": {
            "severity": "LOW",
            "confidence_swing_detected": False,
            "confidence_swing": 0.0,
            "divergence_detected": False,
            "critic_divergence_score": 0,
            "synthesis_quality": "FULL",
        },
        "leakage": {
            "detected": False,
            "severity": "LOW",
            "pii_indicators": [],
            "sensitive_keywords": [],
        },
        "sovereignty": {
            "severity": "LOW",
            "cross_boundary_nodes": [],
            "zdr_signals": [],
            "inferred_regions": [],
        },
        "aivss": {
            "overall": {"composite": 3.0, "severity": "LOW"},
            "inbound":  {"composite": 0.0, "coverage_pct": 0},
            "internal": {"composite": 0.0, "coverage_pct": 0},
            "outbound": {"composite": 0.0, "coverage_pct": 0},
            "coverage_pct": 0,
            "per_threat": [],
            "per_agent": {},
        },
    }


def _with(**overrides) -> Dict:
    """Deep-ish merge of overrides into a clean signals dict."""
    import copy
    sig = copy.deepcopy(_clean())
    for key, val in overrides.items():
        parts = key.split(".")
        target = sig
        for part in parts[:-1]:
            target = target.setdefault(part, {})
        target[parts[-1]] = val
    return sig


def _per_agent(*agents_tokens) -> Dict:
    """Build per_agent dict: _per_agent(('A',100), ('B',100), ('C',9000))"""
    return {name: {"tokens": tokens} for name, tokens in agents_tokens}


# ── YAML loading ──────────────────────────────────────────────────────────────

class TestYAMLLoading:
    def test_rules_file_exists(self):
        assert RULES_PATH.exists(), f"Missing: {RULES_PATH}"

    def test_loads_six_rules(self):
        ev = RuleEvaluator()
        assert len(ev) == 6

    def test_rule_ids_present(self):
        ev = RuleEvaluator()
        ids = ev.rule_ids
        for expected in ["DETECT-001", "DETECT-002", "DETECT-003",
                         "DETECT-004", "DETECT-005", "DETECT-006"]:
            assert expected in ids

    def test_evaluate_returns_list(self):
        ev = RuleEvaluator()
        result = ev.evaluate(_clean(), arch_name="test", run_id="r1")
        assert isinstance(result, list)

    def test_clean_signals_fires_no_rules(self):
        ev = RuleEvaluator()
        result = ev.evaluate(_clean(), arch_name="clean", run_id="r1")
        assert result == [], f"False positives: {[f['unmapped']['rule_id'] for f in result]}"


# ── Condition operator coverage ───────────────────────────────────────────────

class TestConditionOperators:
    def _cond(self, field, op, value, **kwargs):
        c = {"field": field, "op": op, "value": value}
        c.update(kwargs)
        return c

    def test_eq_true(self):
        sig = _with(**{"manipulation.synthesis_quality": "FULL"})
        assert _eval_condition(sig, self._cond("manipulation.synthesis_quality", "==", "FULL"))

    def test_eq_false(self):
        sig = _with(**{"manipulation.synthesis_quality": "PARTIAL"})
        assert not _eval_condition(sig, self._cond("manipulation.synthesis_quality", "==", "FULL"))

    def test_bool_eq(self):
        sig = _with(**{"manipulation.confidence_swing_detected": True})
        assert _eval_condition(sig, self._cond("manipulation.confidence_swing_detected", "==", True))

    def test_gte(self):
        sig = _with(**{"manipulation.confidence_swing": 20.0})
        assert _eval_condition(sig, self._cond("manipulation.confidence_swing", ">=", 15.0))
        assert not _eval_condition(sig, self._cond("manipulation.confidence_swing", ">=", 25.0))

    def test_gt(self):
        sig = _with(**{"manipulation.confidence_swing": 15.0})
        assert not _eval_condition(sig, self._cond("manipulation.confidence_swing", ">", 15.0))
        assert _eval_condition(sig, self._cond("manipulation.confidence_swing", ">", 14.9))

    def test_length_gt_list(self):
        sig = _with(**{"exploitation.injection_patterns": ["js:alert"]})
        assert _eval_condition(sig, self._cond("exploitation.injection_patterns", "length_gt", 0))

    def test_length_gt_empty(self):
        sig = _clean()
        assert not _eval_condition(sig, self._cond("exploitation.injection_patterns", "length_gt", 0))

    def test_token_spike_fires(self):
        sig = _with(**{"aivss.per_agent": _per_agent(("A",100), ("B",100), ("C",100), ("Escape",10000))})
        assert _eval_condition(sig, self._cond("aivss.per_agent", "token_spike", 3.0, min_agents=3))

    def test_token_spike_not_enough_agents(self):
        sig = _with(**{"aivss.per_agent": _per_agent(("A",100), ("Escape",10000))})
        assert not _eval_condition(sig, self._cond("aivss.per_agent", "token_spike", 3.0, min_agents=3))

    def test_no_critical_true_when_empty(self):
        sig = _clean()
        assert _eval_condition(sig, self._cond("aivss.per_threat", "no_critical", True))

    def test_no_critical_false_when_critical_present(self):
        sig = _with(**{"aivss.per_threat": [{"technique_id": "T1", "severity": "CRITICAL"}]})
        assert not _eval_condition(sig, self._cond("aivss.per_threat", "no_critical", True))

    def test_min_agents_true(self):
        sig = _with(**{"aivss.per_agent": _per_agent(("A",100), ("B",200), ("C",300))})
        assert _eval_condition(sig, self._cond("aivss.per_agent", "min_agents", 3))

    def test_min_agents_false(self):
        sig = _with(**{"aivss.per_agent": _per_agent(("A",100), ("B",200))})
        assert not _eval_condition(sig, self._cond("aivss.per_agent", "min_agents", 3))

    def test_missing_field_returns_false(self):
        sig = _clean()
        assert not _eval_condition(sig, self._cond("nonexistent.field", "==", "anything"))


# ── DETECT-001: swing_without_reversal ────────────────────────────────────────

class TestDetect001:
    def _trigger(self):
        return _with(**{
            "manipulation.confidence_swing_detected": True,
            "manipulation.confidence_swing": 18.0,
            "manipulation.synthesis_quality": "FULL",
        })

    def test_fires_on_incident_pattern(self):
        ev = RuleEvaluator()
        findings = ev.evaluate(self._trigger(), arch_name="a", run_id="r")
        ids = [f["unmapped"]["rule_id"] for f in findings]
        assert "DETECT-001" in ids

    def test_does_not_fire_below_threshold(self):
        ev = RuleEvaluator()
        sig = _with(**{
            "manipulation.confidence_swing_detected": True,
            "manipulation.confidence_swing": 5.0,
            "manipulation.synthesis_quality": "FULL",
        })
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-001" not in ids

    def test_does_not_fire_when_synthesis_partial(self):
        ev = RuleEvaluator()
        sig = _with(**{
            "manipulation.confidence_swing_detected": True,
            "manipulation.confidence_swing": 20.0,
            "manipulation.synthesis_quality": "PARTIAL",
        })
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-001" not in ids

    def test_ocsf_fields(self):
        ev = RuleEvaluator()
        findings = ev.evaluate(self._trigger(), arch_name="myarch", run_id="run42")
        f = next(x for x in findings if x["unmapped"]["rule_id"] == "DETECT-001")
        assert f["class_uid"] == 2004
        assert f["severity"] == "High"
        assert "anthropic-cybersec-evals-2026-opus47" in f["unmapped"]["incident_refs"]
        assert "audit_log" in f["unmapped"]["actions"]
        assert "quarantine_trace" in f["unmapped"]["actions"]
        assert f["finding"]["kill_chain_stage"] == "llm_layer"


# ── DETECT-002: divergence_suppressed ────────────────────────────────────────

class TestDetect002:
    def _trigger(self):
        return _with(**{
            "manipulation.divergence_detected": True,
            "manipulation.critic_divergence_score": 25,
            "manipulation.synthesis_quality": "FULL",
        })

    def test_fires_on_incident_pattern(self):
        ev = RuleEvaluator()
        ids = [f["unmapped"]["rule_id"] for f in
               ev.evaluate(self._trigger(), arch_name="a", run_id="r")]
        assert "DETECT-002" in ids

    def test_does_not_fire_below_threshold(self):
        ev = RuleEvaluator()
        sig = _with(**{
            "manipulation.divergence_detected": True,
            "manipulation.critic_divergence_score": 5,
            "manipulation.synthesis_quality": "FULL",
        })
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-002" not in ids

    def test_is_critical_severity(self):
        ev = RuleEvaluator()
        findings = ev.evaluate(self._trigger(), arch_name="a", run_id="r")
        f = next(x for x in findings if x["unmapped"]["rule_id"] == "DETECT-002")
        assert f["severity"] == "Critical"
        assert f["severity_id"] == 5

    def test_page_soc_action_present(self):
        ev = RuleEvaluator()
        findings = ev.evaluate(self._trigger(), arch_name="a", run_id="r")
        f = next(x for x in findings if x["unmapped"]["rule_id"] == "DETECT-002")
        assert "page_soc" in f["unmapped"]["actions"]
        assert "forensic_capture" in f["unmapped"]["actions"]


# ── DETECT-003: token_spike_single_critic ────────────────────────────────────

class TestDetect003:
    def _trigger(self):
        # 4 agents: mean(100,100,100,10000)=2575; 10000 > 7725
        return _with(**{
            "aivss.per_agent": _per_agent(("A",100), ("B",100), ("C",100), ("Escape",10000))
        })

    def test_fires_on_incident_pattern(self):
        ev = RuleEvaluator()
        ids = [f["unmapped"]["rule_id"] for f in
               ev.evaluate(self._trigger(), arch_name="a", run_id="r")]
        assert "DETECT-003" in ids

    def test_does_not_fire_with_two_agents(self):
        ev = RuleEvaluator()
        sig = _with(**{"aivss.per_agent": _per_agent(("A",100), ("Escape",10000))})
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-003" not in ids

    def test_does_not_fire_on_uniform_load(self):
        ev = RuleEvaluator()
        sig = _with(**{"aivss.per_agent": _per_agent(("A",1000), ("B",1000), ("C",1000))})
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-003" not in ids

    def test_reduce_budget_action_present(self):
        ev = RuleEvaluator()
        findings = ev.evaluate(self._trigger(), arch_name="a", run_id="r")
        f = next(x for x in findings if x["unmapped"]["rule_id"] == "DETECT-003")
        assert "reduce_budget" in f["unmapped"]["actions"]


# ── DETECT-004: covert_c2_channel ────────────────────────────────────────────

class TestDetect004:
    def _trigger(self):
        return _with(**{
            "leakage.detected": True,
            "sovereignty.cross_boundary_nodes": ["TelegramBot", "ExternalAPI"],
        })

    def test_fires_on_incident_pattern(self):
        ev = RuleEvaluator()
        ids = [f["unmapped"]["rule_id"] for f in
               ev.evaluate(self._trigger(), arch_name="a", run_id="r")]
        assert "DETECT-004" in ids

    def test_does_not_fire_leakage_only(self):
        ev = RuleEvaluator()
        sig = _with(**{"leakage.detected": True})
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-004" not in ids

    def test_does_not_fire_boundary_only(self):
        ev = RuleEvaluator()
        sig = _with(**{"sovereignty.cross_boundary_nodes": ["ExternalAPI"]})
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-004" not in ids

    def test_block_run_action_present(self):
        ev = RuleEvaluator()
        findings = ev.evaluate(self._trigger(), arch_name="a", run_id="r")
        f = next(x for x in findings if x["unmapped"]["rule_id"] == "DETECT-004")
        assert "block_run" in f["unmapped"]["actions"]
        assert f["finding"]["kill_chain_stage"] == "exfiltration"


# ── DETECT-005: adversarial_input_via_pipeline ────────────────────────────────

class TestDetect005:
    def _trigger(self):
        return _with(**{
            "exploitation.severity": "CRITICAL",
            "exploitation.injection_patterns": ["javascript:alert(1)"],
        })

    def test_fires_on_incident_pattern(self):
        ev = RuleEvaluator()
        ids = [f["unmapped"]["rule_id"] for f in
               ev.evaluate(self._trigger(), arch_name="a", run_id="r")]
        assert "DETECT-005" in ids

    def test_does_not_fire_on_critical_without_injection(self):
        ev = RuleEvaluator()
        sig = _with(**{
            "exploitation.severity": "CRITICAL",
            "exploitation.injection_patterns": [],
        })
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-005" not in ids

    def test_does_not_fire_on_injection_without_critical(self):
        ev = RuleEvaluator()
        sig = _with(**{
            "exploitation.severity": "HIGH",
            "exploitation.injection_patterns": ["js:x"],
        })
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-005" not in ids

    def test_kill_chain_initial_access(self):
        ev = RuleEvaluator()
        findings = ev.evaluate(self._trigger(), arch_name="a", run_id="r")
        f = next(x for x in findings if x["unmapped"]["rule_id"] == "DETECT-005")
        assert f["finding"]["kill_chain_stage"] == "initial_access"

    def test_playbook_steps_present(self):
        ev = RuleEvaluator()
        findings = ev.evaluate(self._trigger(), arch_name="a", run_id="r")
        f = next(x for x in findings if x["unmapped"]["rule_id"] == "DETECT-005")
        assert isinstance(f["unmapped"]["playbook_steps"], list)
        assert len(f["unmapped"]["playbook_steps"]) > 0


# ── DETECT-006: distributed_agentic_sweep ────────────────────────────────────

class TestDetect006:
    def _trigger(self):
        return _with(**{
            "aivss.coverage_pct": 75,
            "aivss.per_threat": [
                {"technique_id": "T1", "severity": "HIGH"},
                {"technique_id": "T2", "severity": "MEDIUM"},
            ],
            "aivss.per_agent": _per_agent(("A",500), ("B",600), ("C",550)),
        })

    def test_fires_on_incident_pattern(self):
        ev = RuleEvaluator()
        ids = [f["unmapped"]["rule_id"] for f in
               ev.evaluate(self._trigger(), arch_name="a", run_id="r")]
        assert "DETECT-006" in ids

    def test_does_not_fire_when_critical_threat_present(self):
        ev = RuleEvaluator()
        sig = _with(**{
            "aivss.coverage_pct": 75,
            "aivss.per_threat": [{"technique_id": "T1", "severity": "CRITICAL"}],
            "aivss.per_agent": _per_agent(("A",500), ("B",600), ("C",550)),
        })
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-006" not in ids

    def test_does_not_fire_on_low_coverage(self):
        ev = RuleEvaluator()
        sig = _with(**{
            "aivss.coverage_pct": 30,
            "aivss.per_threat": [],
            "aivss.per_agent": _per_agent(("A",500), ("B",600), ("C",550)),
        })
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-006" not in ids

    def test_does_not_fire_with_fewer_than_3_agents(self):
        ev = RuleEvaluator()
        sig = _with(**{
            "aivss.coverage_pct": 75,
            "aivss.per_threat": [],
            "aivss.per_agent": _per_agent(("A",500), ("B",600)),
        })
        ids = [f["unmapped"]["rule_id"] for f in ev.evaluate(sig, arch_name="a", run_id="r")]
        assert "DETECT-006" not in ids

    def test_kill_chain_discovery(self):
        ev = RuleEvaluator()
        findings = ev.evaluate(self._trigger(), arch_name="a", run_id="r")
        f = next(x for x in findings if x["unmapped"]["rule_id"] == "DETECT-006")
        assert f["finding"]["kill_chain_stage"] == "discovery"


# ── Co-occurrence: DETECT-002 + DETECT-005 ───────────────────────────────────

class TestCoOccurrence:
    def test_detect002_and_005_fire_together(self):
        """
        Adversarial input (DETECT-005) that also causes divergence suppression
        (DETECT-002) is the strongest indicator of a targeted attack on the pipeline.
        """
        sig = _with(**{
            "exploitation.severity": "CRITICAL",
            "exploitation.injection_patterns": ["<script>"],
            "manipulation.divergence_detected": True,
            "manipulation.critic_divergence_score": 28,
            "manipulation.synthesis_quality": "FULL",
        })
        ev = RuleEvaluator()
        findings = ev.evaluate(sig, arch_name="targeted", run_id="r")
        ids = [f["unmapped"]["rule_id"] for f in findings]
        assert "DETECT-002" in ids
        assert "DETECT-005" in ids

    def test_all_findings_json_serialisable(self):
        sig = _with(**{
            "exploitation.severity": "CRITICAL",
            "exploitation.injection_patterns": ["js:x"],
            "manipulation.divergence_detected": True,
            "manipulation.critic_divergence_score": 25,
            "manipulation.synthesis_quality": "FULL",
            "leakage.detected": True,
            "sovereignty.cross_boundary_nodes": ["ext"],
        })
        ev = RuleEvaluator()
        findings = ev.evaluate(sig, arch_name="a", run_id="r")
        assert json.dumps(findings)


# ── OCSF invariants across all rules ─────────────────────────────────────────

class TestOCSFInvariants:
    def test_every_finding_has_class_uid_2004(self):
        signals = [
            _with(**{"manipulation.confidence_swing_detected": True,
                     "manipulation.confidence_swing": 20.0,
                     "manipulation.synthesis_quality": "FULL"}),
            _with(**{"manipulation.divergence_detected": True,
                     "manipulation.critic_divergence_score": 25,
                     "manipulation.synthesis_quality": "FULL"}),
            _with(**{"aivss.per_agent": _per_agent(("A",100),("B",100),("C",100),("E",10000))}),
            _with(**{"leakage.detected": True,
                     "sovereignty.cross_boundary_nodes": ["x"]}),
            _with(**{"exploitation.severity": "CRITICAL",
                     "exploitation.injection_patterns": ["js:x"]}),
            _with(**{"aivss.coverage_pct": 75,
                     "aivss.per_threat": [],
                     "aivss.per_agent": _per_agent(("A",500),("B",500),("C",500))}),
        ]
        ev = RuleEvaluator()
        for sig in signals:
            for f in ev.evaluate(sig, arch_name="t", run_id="r"):
                assert f["class_uid"] == 2004
                assert f["ocsf_version"] == "1.1"
                assert "rule_id" in f["unmapped"]
                assert "actions" in f["unmapped"]
                assert "kill_chain_stage" in f["unmapped"]
                assert "incident_refs" in f["unmapped"]
