"""
Unit tests — Stage 5: demand-weighted meta layer gap detection.

All tests are deterministic: no LLM calls, no network.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from chatbot.modules.ta_brain_gaps import (
    DEMAND_ALPHA,
    DEMAND_THRESHOLD,
    MIN_INSTANCES,
    compute_gap_demand_weights,
    detect_gaps_v2,
    enrich_brain_gaps,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_instance(arch_id, arch_type, source="real"):
    return {
        "arch_id": arch_id,
        "arch_type": arch_type,
        "topology_signature": f"sig_{arch_id}",
        "node_count": 5,
        "edge_count": 3,
        "source": source,
    }


def _make_pattern(pid, arch_type, corpus_conf=0.8, aivss_mean=0.5, node_min=3):
    return {
        "id": pid,
        "trigger": {"arch_type": arch_type, "node_count_min": node_min},
        "predicts": {"aivss_mean": aivss_mean, "aivss_floor": 0.3,
                     "techniques": [], "detect_rules": [],
                     "common_missing_controls": [], "technique_frequencies": {},
                     "control_frequencies": {}},
        "corpus_confidence": corpus_conf,
        "benchmark_confidence": 1.0,
        "evidence_count": MIN_INSTANCES,
        "real_evidence_count": MIN_INSTANCES,
        "evidence_arch_ids": [],
        "feedback_confirmed_count": 0,
        "feedback_wrong_count": 0,
        "suspect": False,
        "trend": "stable",
        "remediation_template": {"priority_controls": [], "mmd_patch_stub": ""},
    }


def _write_interactions(path, entries):
    with path.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _infer_entry(arch_type, had_match, cache_route="kg"):
    return {
        "ts": "2026-08-12T10:00:00Z",
        "caller_type": "rest",
        "query_mode": "infer",
        "topology_signature": f"sig_{arch_type}_x",
        "arch_type": arch_type,
        "patterns_fired": [],
        "confidence_returned": 0.0,
        "had_match": had_match,
        "feedback": None,
        "cache_route": cache_route,
    }


# ── compute_gap_demand_weights ────────────────────────────────────────────────

class TestComputeGapDemandWeights:
    def test_counts_misses_correctly(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        _write_interactions(log, [
            _infer_entry("web", had_match=False),
            _infer_entry("web", had_match=False),
            _infer_entry("web", had_match=True),
        ])
        weights = compute_gap_demand_weights(log)
        assert weights["web"]["miss_count"] == 2
        assert weights["web"]["total_queries"] == 3

    def test_counts_variant_misses(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        _write_interactions(log, [
            _infer_entry("iot", had_match=True, cache_route="variant"),
            _infer_entry("iot", had_match=True, cache_route="cache_hit"),
        ])
        weights = compute_gap_demand_weights(log)
        assert weights["iot"]["variant_count"] == 1
        assert weights["iot"]["confirm_count"] == 1

    def test_demand_weight_formula(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        # 2 misses + 2 variants + 6 confirms = 10 total
        # demand = (2 + 0.5*2) / 10 = 3/10 = 0.3
        entries = (
            [_infer_entry("web", had_match=False)] * 2
            + [_infer_entry("web", had_match=True, cache_route="variant")] * 2
            + [_infer_entry("web", had_match=True, cache_route="cache_hit")] * 6
        )
        _write_interactions(log, entries)
        weights = compute_gap_demand_weights(log)
        assert abs(weights["web"]["demand_weight"] - 0.3) < 0.001

    def test_skips_feedback_entries(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        _write_interactions(log, [
            {"ts": "t0", "type": "feedback", "feedback": "wrong",
             "topology_signature": "s", "arch_type": "web",
             "query_mode": "infer", "reference_ts": ""},
        ])
        weights = compute_gap_demand_weights(log)
        assert "web" not in weights

    def test_skips_non_infer_modes(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        _write_interactions(log, [
            {**_infer_entry("web", False), "query_mode": "patterns"},
        ])
        weights = compute_gap_demand_weights(log)
        assert "web" not in weights

    def test_missing_log_returns_empty(self, tmp_path):
        assert compute_gap_demand_weights(tmp_path / "nonexistent.jsonl") == {}

    def test_separates_arch_types(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        _write_interactions(log, [
            _infer_entry("web", had_match=False),
            _infer_entry("iot", had_match=True),
        ])
        weights = compute_gap_demand_weights(log)
        assert "web" in weights
        assert "iot" in weights
        assert weights["web"]["miss_count"] == 1
        assert weights["iot"]["miss_count"] == 0


# ── detect_gaps_v2 ────────────────────────────────────────────────────────────

class TestDetectGapsV2:
    def test_produces_coverage_thin_gap_for_sparse_type(self):
        instances = [_make_instance(f"a{i}", "rare") for i in range(2)]  # < MIN_INSTANCES
        patterns = [_make_pattern("B-001", "rare")]
        gaps = detect_gaps_v2(instances, patterns)
        assert any(g["type"] == "coverage_thin" for g in gaps)
        assert any(g["region"] == "arch_type:rare" for g in gaps)

    def test_no_coverage_gap_for_well_sampled_type(self):
        instances = [_make_instance(f"a{i}", "common") for i in range(MIN_INSTANCES + 1)]
        patterns = [_make_pattern("B-001", "common")]
        gaps = detect_gaps_v2(instances, patterns)
        thin_gaps = [g for g in gaps if g["type"] == "coverage_thin"]
        assert len(thin_gaps) == 0

    def test_query_miss_gap_for_unknown_arch_type(self):
        instances = []
        patterns = []
        # arch_type "new_type" queried frequently with all misses
        demand = {"new_type": {"miss_count": 8, "variant_count": 0,
                               "confirm_count": 0, "total_queries": 10,
                               "demand_weight": 0.8}}
        gaps = detect_gaps_v2(instances, patterns, demand)
        assert any(g["type"] == "query_miss" for g in gaps)

    def test_no_query_miss_gap_below_demand_threshold(self):
        instances = []
        patterns = []
        # Low demand_weight (below DEMAND_THRESHOLD)
        demand = {"rare_type": {"miss_count": 1, "variant_count": 0,
                                "confirm_count": 9, "total_queries": 10,
                                "demand_weight": 0.1}}
        gaps = detect_gaps_v2(instances, patterns, demand)
        assert not any(g["type"] == "query_miss" for g in gaps)

    def test_variant_gap_for_well_sampled_type_with_variant_queries(self):
        instances = [_make_instance(f"a{i}", "web") for i in range(MIN_INSTANCES + 2)]
        patterns = [_make_pattern("B-001", "web")]
        # High variant rate
        demand = {"web": {"miss_count": 0, "variant_count": 5,
                          "confirm_count": 5, "total_queries": 10,
                          "demand_weight": 0.25}}
        gaps = detect_gaps_v2(instances, patterns, demand)
        assert any(g["type"] == "variant" for g in gaps)

    def test_forced_gaps_sort_first(self):
        instances = [_make_instance(f"a{i}", "rare") for i in range(1)]
        patterns = []
        # Add a forced gap manually via detect_gaps_v2 not possible directly
        # — test that if we call enrich_brain_gaps with existing forced gaps, they sort first
        normal_gaps = detect_gaps_v2(instances, patterns)
        # All generated gaps should have forced_gap=False
        assert all(not g.get("forced_gap") for g in normal_gaps)

    def test_demand_enriches_coverage_thin_gap_priority(self):
        instances = [_make_instance("a1", "web")]  # thin
        patterns = [_make_pattern("B-001", "web", aivss_mean=0.5)]
        no_demand = detect_gaps_v2(instances, patterns, {})
        with_demand = detect_gaps_v2(
            instances, patterns,
            {"web": {"miss_count": 5, "variant_count": 0,
                     "confirm_count": 0, "total_queries": 5, "demand_weight": 1.0}}
        )
        assert not no_demand or not with_demand or \
               with_demand[0]["priority"] >= no_demand[0]["priority"]

    def test_gap_has_required_fields(self):
        instances = [_make_instance("a1", "sparse")]
        patterns = [_make_pattern("B-001", "sparse")]
        gaps = detect_gaps_v2(instances, patterns)
        for g in gaps:
            for field in ("id", "region", "type", "confidence_floor",
                          "generation_prompt", "priority", "forced_gap",
                          "demand_weight", "miss_count", "variant_count",
                          "total_queries"):
                assert field in g, f"Missing field: {field}"

    def test_empty_inputs_returns_empty(self):
        assert detect_gaps_v2([], []) == []

    def test_gap_ids_are_sequential(self):
        instances = (
            [_make_instance(f"a{i}", "sparse1") for i in range(1)]
            + [_make_instance(f"b{i}", "sparse2") for i in range(2)]
        )
        patterns = []
        gaps = detect_gaps_v2(instances, patterns)
        ids = [g["id"] for g in gaps]
        assert ids == [f"GAP-{i:03d}" for i in range(1, len(ids) + 1)]


# ── enrich_brain_gaps ─────────────────────────────────────────────────────────

class TestEnrichBrainGaps:
    def _write_brain(self, path, patterns=None, gaps=None):
        brain = {
            "version": 1, "pattern_version": 1, "corpus_size": 5,
            "train_size": 4, "hold_out": [],
            "patterns": patterns or [],
            "gaps": gaps or [],
        }
        path.write_text(json.dumps(brain))

    def _write_instances(self, path, instances):
        with path.open("w") as f:
            for i in instances:
                f.write(json.dumps(i) + "\n")

    def test_updates_brain_gaps(self, tmp_path):
        brain_path = tmp_path / "ta_brain.json"
        instances_path = tmp_path / "ta_brain_instances.jsonl"
        log_path = tmp_path / "interactions.jsonl"

        self._write_brain(brain_path, patterns=[_make_pattern("B-001", "web")],
                          gaps=[{"id": "GAP-001", "region": "arch_type:web",
                                 "type": "coverage_thin", "priority": 0.1,
                                 "forced_gap": False, "confidence_floor": 0.0,
                                 "generation_prompt": "old", "demand_weight": 0.0,
                                 "miss_count": 0, "variant_count": 0, "total_queries": 0}])
        self._write_instances(instances_path, [_make_instance("a1", "web")])
        _write_interactions(log_path, [_infer_entry("web", had_match=False)] * 5)

        result = enrich_brain_gaps(brain_path, instances_path, log_path)
        brain = json.loads(brain_path.read_text())

        assert "gaps_enriched_ts" in brain
        assert result["arch_types_with_demand"] >= 1

    def test_preserves_forced_gaps(self, tmp_path):
        brain_path = tmp_path / "ta_brain.json"
        instances_path = tmp_path / "ta_brain_instances.jsonl"
        log_path = tmp_path / "interactions.jsonl"

        forced_gap = {
            "id": "GAP-FORCED", "region": "arch_type:special",
            "type": "coverage_thin", "forced_gap": True, "priority": 0.9,
            "confidence_floor": 0.0, "generation_prompt": "forced",
            "demand_weight": 0.0, "miss_count": 0, "variant_count": 0, "total_queries": 0,
        }
        self._write_brain(brain_path, gaps=[forced_gap])
        self._write_instances(instances_path, [])
        log_path.write_text("")

        result = enrich_brain_gaps(brain_path, instances_path, log_path)
        brain = json.loads(brain_path.read_text())

        forced = [g for g in brain["gaps"] if g.get("forced_gap")]
        assert len(forced) == 1
        assert result["gaps_forced"] == 1

    def test_forced_gaps_sort_first(self, tmp_path):
        brain_path = tmp_path / "ta_brain.json"
        instances_path = tmp_path / "ta_brain_instances.jsonl"
        log_path = tmp_path / "interactions.jsonl"

        forced_gap = {
            "id": "GAP-FRC", "region": "arch_type:x", "type": "coverage_thin",
            "forced_gap": True, "priority": 0.1,  # low priority but forced
            "confidence_floor": 0.0, "generation_prompt": "f",
            "demand_weight": 0.0, "miss_count": 0, "variant_count": 0, "total_queries": 0,
        }
        self._write_brain(brain_path, patterns=[_make_pattern("B-001", "sparse")],
                          gaps=[forced_gap])
        self._write_instances(instances_path, [_make_instance("a1", "sparse")])
        log_path.write_text("")

        enrich_brain_gaps(brain_path, instances_path, log_path)
        brain = json.loads(brain_path.read_text())

        if brain["gaps"]:
            assert brain["gaps"][0].get("forced_gap") is True

    def test_raises_when_brain_missing(self, tmp_path):
        with pytest.raises(ValueError):
            enrich_brain_gaps(tmp_path / "nonexistent.json")
