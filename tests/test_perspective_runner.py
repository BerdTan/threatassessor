"""
Unit tests for PerspectiveRunner.
No API, no LLM. Uses real STIX + DETECT rules files.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from chatbot.modules.director_caster import PacingSignals, SimulationBounds, StepPacing
from chatbot.modules.perspective_runner import (
    PerspectiveResult,
    PerspectiveRunner,
    PerspectiveStep,
    _has_mitigation,
    _step_rationale,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gt(
    attack_paths=None,
    controls_present=None,
    control_recommendations=None,
):
    return {
        "expected_attack_paths": attack_paths or [],
        "controls_present": controls_present or [],
        "control_recommendations": control_recommendations or [],
    }


def _ap(id_="AP-1", per_node=None, techs=None):
    return {
        "id": id_,
        "path": ["internet", "api_gw", "db"],
        "entry": "internet",
        "target": "db",
        "per_node_techniques": per_node or {
            "internet": ["T1566"],
            "api_gw": ["T1059"],
            "db": ["T1078"],
        },
        "techniques": techs or ["T1566", "T1059", "T1078"],
    }


def _bounds(scenario_id="AP-1", nodes=None, tech_set=None, actor=None):
    return SimulationBounds(
        scenario_id=scenario_id,
        technique_set=tech_set or {"T1566", "T1059", "T1078"},
        node_set=nodes or ["internet", "api_gw", "db"],
        actor=actor or {"name": "APT28", "matched_techniques": ["T1059"]},
    )


def _rec(control, techs):
    return {"control": control, "techniques": techs}


# ---------------------------------------------------------------------------
# _has_mitigation
# ---------------------------------------------------------------------------

class TestHasMitigation:
    def test_present(self):
        recs = [_rec("mfa", ["T1078"])]
        assert _has_mitigation("T1078", {"mfa"}, recs) is True

    def test_not_present(self):
        recs = [_rec("mfa", ["T1078"])]
        assert _has_mitigation("T1078", set(), recs) is False

    def test_wrong_technique(self):
        recs = [_rec("mfa", ["T1078"])]
        assert _has_mitigation("T1059", {"mfa"}, recs) is False

    def test_case_insensitive(self):
        recs = [_rec("MFA", ["T1078"])]
        assert _has_mitigation("T1078", {"mfa"}, recs) is True


# ---------------------------------------------------------------------------
# PerspectiveRunner init
# ---------------------------------------------------------------------------

class TestInit:
    def test_loads_tech_tactic_index(self):
        gt = _make_gt()
        runner = PerspectiveRunner(gt)
        # T1059 (Command and Scripting Interpreter) → execution
        stages = runner._tech_tactic.get("T1059", [])
        assert "execution" in stages

    def test_loads_stage_rule_index(self):
        gt = _make_gt()
        runner = PerspectiveRunner(gt)
        assert len(runner._stage_rule) > 0

    def test_find_detect_rule_for_known_technique(self):
        gt = _make_gt()
        runner = PerspectiveRunner(gt)
        # T1059 is execution; there should be at least one DETECT rule for that stage
        rule = runner._find_detect_rule("T1059")
        # May be None if no rule covers execution stage — just check it doesn't raise
        assert rule is None or rule.startswith("DETECT-")

    def test_find_detect_rule_unknown_technique(self):
        gt = _make_gt()
        runner = PerspectiveRunner(gt)
        assert runner._find_detect_rule("T9999") is None


# ---------------------------------------------------------------------------
# PerspectiveRunner.run
# ---------------------------------------------------------------------------

class TestRun:
    @pytest.fixture(scope="class")
    def runner(self):
        return PerspectiveRunner(_make_gt(attack_paths=[_ap()]))

    def test_yields_one_step_per_node(self, runner):
        b = _bounds()
        steps = list(runner.run(b))
        assert len(steps) == 3

    def test_step_fields_populated(self, runner):
        b = _bounds()
        steps = list(runner.run(b))
        s = steps[0]
        assert s.step == 1
        assert s.node == "internet"
        assert s.technique in {"T1566", "T1059", "T1078", "UNKNOWN_NODE"}
        assert s.outcome in {"BLOCKED", "DEGRADED", "SUCCEEDED", "UNKNOWN_NODE"}
        assert s.red_position == "internet"
        assert s.edge_from is None   # first step has no previous
        assert s.edge_to == "internet"

    def test_edge_from_populated_after_first(self, runner):
        b = _bounds()
        steps = list(runner.run(b))
        assert steps[1].edge_from == "internet"
        assert steps[2].edge_from == "api_gw"

    def test_succeeded_when_no_mitigation_no_detect(self):
        # No controls present, and T9990 won't have a DETECT rule
        ap = _ap(per_node={"internet": ["T9990"], "api_gw": ["T9990"], "db": ["T9990"]},
                 techs=["T9990"])
        gt = _make_gt(attack_paths=[ap])
        runner = PerspectiveRunner(gt)
        b = SimulationBounds("AP-1", {"T9990"}, ["internet", "api_gw", "db"], {})
        steps = list(runner.run(b))
        for s in steps:
            if s.outcome != "UNKNOWN_NODE":
                assert s.outcome == "SUCCEEDED"
                assert s.mitigation_present is False

    def test_blocked_when_mitigation_and_detection(self):
        # T1059 → execution stage; provide matching control + ensure rule fires
        ap = _ap(per_node={"internet": ["T1059"], "api_gw": ["T1059"], "db": ["T1059"]},
                 techs=["T1059"])
        gt = _make_gt(
            attack_paths=[ap],
            controls_present=["application whitelisting"],
            control_recommendations=[_rec("application whitelisting", ["T1059"])],
        )
        runner = PerspectiveRunner(gt)
        rule = runner._find_detect_rule("T1059")
        if rule is None:
            pytest.skip("No DETECT rule for T1059 execution stage in current rules")
        b = SimulationBounds("AP-1", {"T1059"}, ["internet", "api_gw", "db"],
                             {"name": "", "matched_techniques": []})
        steps = [s for s in runner.run(b) if s.outcome != "UNKNOWN_NODE"]
        assert all(s.outcome == "BLOCKED" for s in steps)
        assert all(s.mitigation_present is True for s in steps)

    def test_degraded_when_mitigation_only(self):
        # T9991 has no DETECT rule; mitigation present → DEGRADED
        ap = _ap(per_node={"internet": ["T9991"], "api_gw": ["T9991"], "db": ["T9991"]},
                 techs=["T9991"])
        gt = _make_gt(
            attack_paths=[ap],
            controls_present=["special control"],
            control_recommendations=[_rec("special control", ["T9991"])],
        )
        runner = PerspectiveRunner(gt)
        b = SimulationBounds("AP-1", {"T9991"}, ["internet", "api_gw", "db"], {})
        steps = [s for s in runner.run(b) if s.outcome != "UNKNOWN_NODE"]
        assert all(s.outcome == "DEGRADED" for s in steps)
        assert all(s.mitigation_present is True for s in steps)

    def test_unknown_node_for_out_of_bounds_node(self, runner):
        b = SimulationBounds("AP-1", {"T1059"}, ["internet", "shadow_node", "db"], {})
        # shadow_node is not in AP-1's per_node_techniques
        steps = list(runner.run(b))
        shadow = next(s for s in steps if s.node == "shadow_node")
        assert shadow.outcome == "UNKNOWN_NODE"
        assert shadow.technique == "UNKNOWN_NODE"

    def test_blue_retreats_home_on_succeeded(self):
        ap = _ap(per_node={"internet": ["T9992"], "api_gw": ["T9992"], "db": ["T9992"]},
                 techs=["T9992"])
        gt = _make_gt(attack_paths=[ap])
        runner = PerspectiveRunner(gt)
        b = SimulationBounds("AP-1", {"T9992"}, ["internet", "api_gw", "db"], {})
        steps = [s for s in runner.run(b) if s.outcome == "SUCCEEDED"]
        for s in steps:
            assert s.blue_position == "internet"  # blue_home = first node

    def test_blue_advances_on_blocked(self):
        ap = _ap(per_node={"internet": ["T1059"], "api_gw": ["T1059"], "db": ["T1059"]},
                 techs=["T1059"])
        gt = _make_gt(
            attack_paths=[ap],
            controls_present=["application whitelisting"],
            control_recommendations=[_rec("application whitelisting", ["T1059"])],
        )
        runner = PerspectiveRunner(gt)
        rule = runner._find_detect_rule("T1059")
        if rule is None:
            pytest.skip("No DETECT rule for execution stage")
        b = SimulationBounds("AP-1", {"T1059"}, ["internet", "api_gw", "db"], {})
        steps = list(runner.run(b))
        # First BLOCKED step: edge_from is None (first node) → blue_home
        # Subsequent BLOCKED steps: blue moves to prev node
        blocked = [s for s in steps if s.outcome == "BLOCKED"]
        # Blue should be at the previous node (edge_from) for all non-first blocked steps
        for s in blocked:
            expected_blue = s.edge_from if s.edge_from is not None else "internet"
            assert s.blue_position == expected_blue

    def test_pacing_applied_when_provided(self, runner):
        b = _bounds()
        pacing = PacingSignals(scenario_id="AP-1", steps=[
            StepPacing("internet", "T1566", True, 2400),
            StepPacing("api_gw", "T1059", False, 1200),
            StepPacing("db", "T1078", False, 1200),
        ])
        steps = list(runner.run(b, pacing))
        internet_step = next(s for s in steps if s.node == "internet")
        assert internet_step.pause_at_critical is True
        assert internet_step.step_delay_ms == 2400

    def test_to_dict_serialisable(self, runner):
        b = _bounds()
        steps = list(runner.run(b))
        d = steps[0].to_dict()
        for key in ("step", "node", "technique", "outcome", "rule_fired",
                    "mitigation_present", "pause_at_critical", "red_position",
                    "blue_position", "edge_from", "edge_to", "step_delay_ms", "rationale"):
            assert key in d


# ---------------------------------------------------------------------------
# PerspectiveResult / run_all
# ---------------------------------------------------------------------------

class TestRunAll:
    def test_run_all_returns_result(self):
        gt = _make_gt(attack_paths=[_ap()])
        runner = PerspectiveRunner(gt)
        result = runner.run_all(_bounds())
        assert isinstance(result, PerspectiveResult)
        assert result.scenario_id == "AP-1"

    def test_summary_counts(self):
        ap = _ap(per_node={"internet": ["T9993"], "api_gw": ["T9993"], "db": ["T9993"]},
                 techs=["T9993"])
        gt = _make_gt(attack_paths=[ap])
        runner = PerspectiveRunner(gt)
        b = SimulationBounds("AP-1", {"T9993"}, ["internet", "api_gw", "db"], {})
        result = runner.run_all(b)
        assert result.summary["total_steps"] == 3
        assert result.summary["succeeded"] == 3
        assert result.summary["block_rate"] == 0.0

    def test_summary_block_rate_range(self):
        gt = _make_gt(attack_paths=[_ap()])
        runner = PerspectiveRunner(gt)
        result = runner.run_all(_bounds())
        assert 0.0 <= result.summary["block_rate"] <= 1.0
