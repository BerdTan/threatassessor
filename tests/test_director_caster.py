"""
Unit tests for DirectorCaster.
No API, no LLM — driven entirely by synthetic ground_truth fixtures.
"""
from __future__ import annotations
import sys
from pathlib import Path
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from chatbot.modules.director_caster import (
    DirectorCaster,
    ScenarioManifest,
    SimulationBounds,
    PacingSignals,
    _estimate_block_rate,
    _normalise_criticalities,
    _risk_badge,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_gt(
    attack_paths=None,
    controls_present=None,
    control_recommendations=None,
    threat_actors=None,
) -> dict:
    return {
        "expected_attack_paths": attack_paths or [],
        "controls_present": controls_present or [],
        "control_recommendations": control_recommendations or [],
        "threat_actors": threat_actors or [],
    }


def _ap(id_="AP-1", entry="internet", target="db", techs=None, criticality=0.8,
        per_node=None, matched_actors=None):
    return {
        "id": id_,
        "entry": entry,
        "target": target,
        "techniques": techs or ["T1059", "T1078"],
        "criticality": criticality,
        "path": ["internet", "api_gw", "db"],
        "per_node_techniques": per_node or {
            "internet": ["T1566"],
            "api_gw": ["T1059"],
            "db": ["T1078"],
        },
        "matched_actors": matched_actors,
    }


def _actor(name="APT28", overlap=0.6, matched=None, tools=None):
    return {
        "group_id": "G0007",
        "name": name,
        "aliases": [name],
        "overlap_pct": overlap,
        "matched_techniques": matched or ["T1059", "T1078"],
        "tools": tools or ["Mimikatz"],
    }


def _rec(control, techs, present=True):
    return {"control": control, "techniques": techs}


# ---------------------------------------------------------------------------
# _risk_badge
# ---------------------------------------------------------------------------

class TestRiskBadge:
    def test_critical(self):
        assert _risk_badge(0.9) == "CRITICAL"

    def test_high(self):
        assert _risk_badge(0.6) == "HIGH"

    def test_med(self):
        assert _risk_badge(0.4) == "MED"

    def test_low(self):
        assert _risk_badge(0.1) == "LOW"

    def test_zero(self):
        assert _risk_badge(0.0) == "LOW"


# ---------------------------------------------------------------------------
# _estimate_block_rate
# ---------------------------------------------------------------------------

class TestBlockRate:
    def test_all_blocked(self):
        ap = _ap(techs=["T1059", "T1078"])
        recs = [_rec("mfa", ["T1078"]), _rec("edr", ["T1059"])]
        cp = {"mfa", "edr"}
        rate = _estimate_block_rate(ap, cp, recs)
        assert rate == 1.0

    def test_none_blocked(self):
        ap = _ap(techs=["T1059", "T1078"])
        recs = [_rec("mfa", ["T1078"]), _rec("edr", ["T1059"])]
        rate = _estimate_block_rate(ap, set(), recs)
        assert rate == 0.0

    def test_half_blocked(self):
        ap = _ap(techs=["T1059", "T1078"])
        recs = [_rec("mfa", ["T1078"])]
        rate = _estimate_block_rate(ap, {"mfa"}, recs)
        assert rate == 0.5

    def test_empty_techniques(self):
        ap = _ap(techs=[])
        assert _estimate_block_rate(ap, {"mfa"}, []) == 0.0

    def test_case_insensitive_match(self):
        ap = _ap(techs=["T1078"])
        recs = [_rec("MFA", ["T1078"])]
        rate = _estimate_block_rate(ap, {"mfa"}, recs)
        assert rate == 1.0


# ---------------------------------------------------------------------------
# _normalise_criticalities
# ---------------------------------------------------------------------------

class TestNormaliseCriticalities:
    def test_single_path(self):
        aps = [_ap("AP-1", criticality=0.8)]
        norms = _normalise_criticalities(aps)
        assert norms["AP-1"] == pytest.approx(1.0)

    def test_relative_ordering(self):
        aps = [_ap("AP-1", criticality=0.4), _ap("AP-2", criticality=0.8)]
        norms = _normalise_criticalities(aps)
        assert norms["AP-1"] < norms["AP-2"]
        assert norms["AP-2"] == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# ScenarioManifest
# ---------------------------------------------------------------------------

class TestBuildManifest:
    def test_returns_manifest(self):
        gt = _make_gt(attack_paths=[_ap()])
        dc = DirectorCaster(gt)
        manifest = dc.build_manifest()
        assert isinstance(manifest, ScenarioManifest)
        assert len(manifest.scenarios) == 1

    def test_sorted_descending_by_score(self):
        # High criticality + actor should rank above low
        gt = _make_gt(attack_paths=[
            _ap("AP-1", criticality=0.1, matched_actors=[_actor(overlap=0.1)]),
            _ap("AP-2", criticality=0.9, matched_actors=[_actor(overlap=0.9)]),
        ])
        dc = DirectorCaster(gt)
        manifest = dc.build_manifest()
        scores = [s.composite_risk_score for s in manifest.scenarios]
        assert scores == sorted(scores, reverse=True)

    def test_get_by_id(self):
        gt = _make_gt(attack_paths=[_ap("AP-1"), _ap("AP-2")])
        dc = DirectorCaster(gt)
        manifest = dc.build_manifest()
        assert manifest.get("AP-1") is not None
        assert manifest.get("AP-99") is None

    def test_composite_score_range(self):
        gt = _make_gt(
            attack_paths=[_ap(matched_actors=[_actor()])],
            controls_present=["mfa"],
            control_recommendations=[_rec("mfa", ["T1078"])],
        )
        dc = DirectorCaster(gt)
        manifest = dc.build_manifest()
        for s in manifest.scenarios:
            assert 0.0 <= s.composite_risk_score <= 1.0

    def test_risk_badge_set(self):
        gt = _make_gt(attack_paths=[_ap(criticality=0.95, matched_actors=[_actor(overlap=0.9)])])
        dc = DirectorCaster(gt)
        manifest = dc.build_manifest()
        assert manifest.scenarios[0].risk_badge in {"CRITICAL", "HIGH", "MED", "LOW"}

    def test_actor_name_populated(self):
        actor = _actor("APT29", overlap=0.7)
        gt = _make_gt(attack_paths=[_ap(matched_actors=[actor])])
        dc = DirectorCaster(gt)
        manifest = dc.build_manifest()
        assert manifest.scenarios[0].actor_name == "APT29"

    def test_arch_actors_passthrough(self):
        actors = [_actor("FIN7")]
        gt = _make_gt(attack_paths=[_ap()], threat_actors=actors)
        dc = DirectorCaster(gt)
        manifest = dc.build_manifest()
        assert manifest.arch_actors == actors

    def test_to_dict_serialisable(self):
        gt = _make_gt(attack_paths=[_ap(matched_actors=[_actor()])])
        dc = DirectorCaster(gt)
        d = dc.build_manifest().to_dict()
        assert "scenarios" in d
        assert "arch_actors" in d
        s = d["scenarios"][0]
        for key in ("scenario_id", "path_label", "composite_risk_score",
                    "risk_badge", "block_rate_estimate", "actor_overlap_pct",
                    "actor_name", "risk_rationale"):
            assert key in s

    def test_empty_paths(self):
        gt = _make_gt()
        dc = DirectorCaster(gt)
        manifest = dc.build_manifest()
        assert manifest.scenarios == []


# ---------------------------------------------------------------------------
# SimulationBounds
# ---------------------------------------------------------------------------

class TestBuildBounds:
    def test_technique_set_populated(self):
        gt = _make_gt(attack_paths=[_ap("AP-1")])
        dc = DirectorCaster(gt)
        bounds = dc.build_bounds("AP-1")
        assert isinstance(bounds, SimulationBounds)
        assert "T1059" in bounds.technique_set

    def test_node_set_ordered(self):
        gt = _make_gt(attack_paths=[_ap("AP-1")])
        dc = DirectorCaster(gt)
        bounds = dc.build_bounds("AP-1")
        assert bounds.node_set == ["internet", "api_gw", "db"]

    def test_allows_technique(self):
        gt = _make_gt(attack_paths=[_ap("AP-1")])
        dc = DirectorCaster(gt)
        bounds = dc.build_bounds("AP-1")
        assert bounds.allows_technique("T1059")
        assert not bounds.allows_technique("T9999")

    def test_allows_node(self):
        gt = _make_gt(attack_paths=[_ap("AP-1")])
        dc = DirectorCaster(gt)
        bounds = dc.build_bounds("AP-1")
        assert bounds.allows_node("api_gw")
        assert not bounds.allows_node("shadow_node")

    def test_unknown_scenario_returns_empty_bounds(self):
        gt = _make_gt(attack_paths=[_ap("AP-1")])
        dc = DirectorCaster(gt)
        bounds = dc.build_bounds("AP-99")
        assert bounds.technique_set == set()
        assert bounds.node_set == []

    def test_actor_populated_from_path(self):
        actor = _actor("Lazarus")
        gt = _make_gt(attack_paths=[_ap("AP-1", matched_actors=[actor])])
        dc = DirectorCaster(gt)
        bounds = dc.build_bounds("AP-1")
        assert bounds.actor["name"] == "Lazarus"

    def test_actor_falls_back_to_arch(self):
        arch_actor = _actor("APT41")
        gt = _make_gt(attack_paths=[_ap("AP-1", matched_actors=None)], threat_actors=[arch_actor])
        dc = DirectorCaster(gt)
        bounds = dc.build_bounds("AP-1")
        assert bounds.actor["name"] == "APT41"


# ---------------------------------------------------------------------------
# PacingSignals
# ---------------------------------------------------------------------------

class TestBuildPacing:
    def _bounds(self, scenario_id="AP-1", actor_techs=None):
        return SimulationBounds(
            scenario_id=scenario_id,
            technique_set={"T1059", "T1078", "T1566"},
            node_set=["internet", "api_gw", "db"],
            actor={"matched_techniques": actor_techs or ["T1059"]},
        )

    def test_returns_pacing(self):
        gt = _make_gt(attack_paths=[_ap("AP-1")])
        dc = DirectorCaster(gt)
        pacing = dc.build_pacing(self._bounds())
        assert isinstance(pacing, PacingSignals)
        assert len(pacing.steps) == 3  # 3 nodes in path

    def test_critical_step_when_actor_tech_matches(self):
        # api_gw has T1059, actor knows T1059 → pause_at_critical=True
        gt = _make_gt(attack_paths=[_ap("AP-1")])
        dc = DirectorCaster(gt)
        pacing = dc.build_pacing(self._bounds(actor_techs=["T1059"]))
        api_gw_step = next(s for s in pacing.steps if s.node_id == "api_gw")
        assert api_gw_step.pause_at_critical is True
        assert api_gw_step.step_delay_ms == 2400

    def test_non_critical_step_normal_delay(self):
        # db has T1078, actor doesn't know T1078 → no pause
        gt = _make_gt(attack_paths=[_ap("AP-1")])
        dc = DirectorCaster(gt)
        pacing = dc.build_pacing(self._bounds(actor_techs=["T1566"]))
        db_step = next(s for s in pacing.steps if s.node_id == "db")
        # db has T1078, actor has T1566 → no overlap
        assert db_step.step_delay_ms == 1200

    def test_unknown_scenario_returns_empty_pacing(self):
        gt = _make_gt(attack_paths=[_ap("AP-1")])
        dc = DirectorCaster(gt)
        bounds = SimulationBounds("AP-99", set(), [], {})
        pacing = dc.build_pacing(bounds)
        assert pacing.steps == []

    def test_for_node_lookup(self):
        gt = _make_gt(attack_paths=[_ap("AP-1")])
        dc = DirectorCaster(gt)
        pacing = dc.build_pacing(self._bounds())
        step = pacing.for_node("api_gw")
        assert step is not None
        assert step.node_id == "api_gw"
        assert pacing.for_node("unknown") is None
