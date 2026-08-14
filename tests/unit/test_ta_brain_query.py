"""
Unit + integration tests — Stage 2: TA Brain query engine.

All tests are deterministic: no LLM calls, no network.
Tests that need ta_brain.json use a seeded tmp_path fixture.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from chatbot.modules.ta_brain_query import (
    VALID_MODES,
    _log_interaction,
    _run_infer,
    query_brain,
)
from chatbot.modules.ta_brain_cache import reset_singleton as _reset_cache_singleton


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path):
    """Reset cache singleton before each test, redirect to tmp_path to avoid file bleed."""
    _reset_cache_singleton()
    with patch("chatbot.modules.ta_brain_cache.CACHE_PATH",
               tmp_path / "ta_brain_cache.json"):
        _reset_cache_singleton()
        yield
    _reset_cache_singleton()


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _make_brain(patterns=None, gaps=None, pattern_version=1) -> dict:
    return {
        "version": 1,
        "pattern_version": pattern_version,
        "built_ts": "2026-08-12T00:00:00Z",
        "corpus_size": 5,
        "train_size": 4,
        "hold_out": [],
        "patterns": patterns or [],
        "gaps": gaps or [],
    }


def _make_pattern(
    pid, arch_type, techniques, controls, detect_rules=None,
    corpus_conf=0.8, aivss_floor=0.3, aivss_mean=0.5,
    evidence_ids=None,
):
    return {
        "id": pid,
        "trigger": {"arch_type": arch_type, "node_count_min": 3},
        "predicts": {
            "techniques": techniques,
            "technique_frequencies": {t: round(corpus_conf, 3) for t in techniques},
            "detect_rules": detect_rules or [],
            "aivss_floor": aivss_floor,
            "aivss_mean": aivss_mean,
            "common_missing_controls": controls,
            "control_frequencies": {c: round(corpus_conf, 3) for c in controls},
        },
        "remediation_template": {"priority_controls": controls[:3], "mmd_patch_stub": "# patch"},
        "corpus_confidence": corpus_conf,
        "benchmark_confidence": 1.0,
        "evidence_count": 3,
        "real_evidence_count": 3,
        "evidence_arch_ids": evidence_ids or ["arch_a", "arch_b"],
        "trend": "stable",
    }


def _make_instance(arch_id, arch_type, topology_sig) -> dict:
    return {
        "arch_id": arch_id,
        "arch_type": arch_type,
        "topology_signature": topology_sig,
        "node_count": 5,
        "edge_count": 4,
        "techniques": ["T1078"],
        "controls_missing": ["mfa"],
        "hub_nodes": [],
        "aivss_composite": 0.4,
        "aivss_severity": "LOW",
        "fired_detect_rules": [],
        "run_ts": "2026-08-01T00:00:00Z",
        "source": "real",
    }


@pytest.fixture
def brain_dir(tmp_path):
    """Returns tmp_path with brain + instances + no interactions yet."""
    return tmp_path


def _write_brain(brain_dir, brain_dict):
    (brain_dir / "ta_brain.json").write_text(json.dumps(brain_dict))


def _write_instances(brain_dir, instances):
    path = brain_dir / "ta_brain_instances.jsonl"
    with path.open("a") as f:
        for inst in instances:
            f.write(json.dumps(inst) + "\n")


# ── _run_infer ────────────────────────────────────────────────────────────────

class TestRunInfer:
    def test_returns_had_match_false_when_no_patterns(self):
        result = _run_infer("sig_abc", "web", _make_brain())
        assert result["had_match"] is False
        assert result["patterns_fired"] == []
        assert result["confidence"] == 0.0

    def test_matches_by_arch_type(self):
        pat = _make_pattern("BRAIN-001", "web", ["T1078", "T1059"], ["mfa", "waf"])
        brain = _make_brain(patterns=[pat])
        result = _run_infer("any_sig", "web", brain)
        assert result["had_match"] is True
        assert "BRAIN-001" in result["patterns_fired"]
        assert "T1078" in result["predictions"]["techniques"]

    def test_no_match_for_wrong_arch_type(self):
        pat = _make_pattern("BRAIN-001", "iot", ["T1078"], ["mfa"])
        brain = _make_brain(patterns=[pat])
        result = _run_infer("any_sig", "web", brain)
        assert result["had_match"] is False

    def test_published_confidence_is_min_of_corpus_and_benchmark(self):
        pat = _make_pattern("BRAIN-001", "web", ["T1078"], ["mfa"],
                            corpus_conf=0.6)
        pat["benchmark_confidence"] = 0.4  # weaker signal limits
        brain = _make_brain(patterns=[pat])
        result = _run_infer("any_sig", "web", brain)
        assert result["confidence"] == 0.4

    def test_returns_techniques_sorted_by_frequency(self):
        pat = _make_pattern("BRAIN-001", "web", ["T1059", "T1078"], ["mfa"])
        pat["predicts"]["technique_frequencies"] = {"T1078": 0.9, "T1059": 0.5}
        brain = _make_brain(patterns=[pat])
        result = _run_infer("any_sig", "web", brain)
        techs = result["predictions"]["technique_top"]
        freqs = [t["frequency"] for t in techs]
        assert freqs == sorted(freqs, reverse=True)

    def test_evidence_trace_contains_pattern_id_and_source_archs(self):
        pat = _make_pattern("BRAIN-001", "web", ["T1078"], ["mfa"],
                            evidence_ids=["arch_x", "arch_y"])
        brain = _make_brain(patterns=[pat])
        result = _run_infer("any_sig", "web", brain)
        assert "BRAIN-001" in result["evidence"]["pattern_ids"]
        assert "arch_x" in result["evidence"]["source_archs"]

    def test_merges_predictions_from_multiple_matching_patterns(self):
        pat1 = _make_pattern("BRAIN-001", "web", ["T1078"], ["mfa"])
        pat2 = _make_pattern("BRAIN-002", "web", ["T1059"], ["waf"])
        brain = _make_brain(patterns=[pat1, pat2])
        result = _run_infer("any_sig", "web", brain)
        assert "T1078" in result["predictions"]["techniques"]
        assert "T1059" in result["predictions"]["techniques"]
        assert len(result["patterns_fired"]) == 2

    def test_aivss_floor_is_minimum_across_patterns(self):
        pat1 = _make_pattern("BRAIN-001", "web", [], [], aivss_floor=0.2)
        pat2 = _make_pattern("BRAIN-002", "web", [], [], aivss_floor=0.6)
        brain = _make_brain(patterns=[pat1, pat2])
        result = _run_infer("any_sig", "web", brain)
        assert result["predictions"]["aivss_floor"] == 0.2


# ── _log_interaction ──────────────────────────────────────────────────────────

class TestLogInteraction:
    def test_appends_to_jsonl(self, tmp_path):
        log_path = tmp_path / "ta_brain_interactions.jsonl"
        with patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path):
            _log_interaction("rest", "infer", "sig_abc", "web", ["BRAIN-001"], 0.8, True)
            _log_interaction("mcp", "gaps", "", "", [], 0.0, False)

        lines = log_path.read_text().strip().splitlines()
        assert len(lines) == 2
        entry = json.loads(lines[0])
        assert entry["caller_type"] == "rest"
        assert entry["query_mode"] == "infer"
        assert entry["had_match"] is True
        assert entry["feedback"] is None

    def test_entry_has_all_required_fields(self, tmp_path):
        log_path = tmp_path / "ta_brain_interactions.jsonl"
        with patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path):
            _log_interaction("harness", "infer", "sig_x", "iot", [], 0.5, False)

        entry = json.loads(log_path.read_text())
        for field in ("ts", "caller_type", "query_mode", "topology_signature",
                      "arch_type", "patterns_fired", "confidence_returned",
                      "had_match", "feedback"):
            assert field in entry, f"Missing field: {field}"

    def test_does_not_raise_on_write_failure(self, tmp_path):
        bad_path = tmp_path / "nonexistent" / "log.jsonl"
        with patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", bad_path):
            # Must not raise
            _log_interaction("rest", "infer", "", "", [], 0.0, False)


# ── query_brain ───────────────────────────────────────────────────────────────

class TestQueryBrain:
    def _setup(self, brain_dir, patterns=None, gaps=None, instances=None):
        _write_brain(brain_dir, _make_brain(patterns=patterns, gaps=gaps))
        if instances:
            _write_instances(brain_dir, instances)

    def _patch_paths(self, brain_dir):
        return [
            patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                  brain_dir / "ta_brain.json"),
            patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                  brain_dir / "ta_brain_instances.jsonl"),
            patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH",
                  brain_dir / "ta_brain_interactions.jsonl"),
            patch("chatbot.modules.ta_brain_query._brain_version", -1),
        ]

    def test_infer_returns_error_for_unknown_arch_name(self, brain_dir):
        self._setup(brain_dir)
        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   brain_dir / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   brain_dir / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH",
                   brain_dir / "ta_brain_interactions.jsonl"), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1):
            result = query_brain(mode="infer", arch_name="nonexistent_arch")
        assert "error" in result

    def test_infer_resolves_arch_name_to_topology_sig(self, brain_dir):
        pat = _make_pattern("BRAIN-001", "web", ["T1078"], ["mfa"])
        self._setup(
            brain_dir,
            patterns=[pat],
            instances=[_make_instance("my_arch", "web", "sig_web_001")],
        )
        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   brain_dir / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   brain_dir / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH",
                   brain_dir / "ta_brain_interactions.jsonl"), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1):
            result = query_brain(mode="infer", arch_name="my_arch")
        assert result["arch_type"] == "web"
        assert result["topology_signature"] == "sig_web_001"

    def test_infer_logs_interaction(self, brain_dir):
        pat = _make_pattern("BRAIN-001", "web", ["T1078"], ["mfa"])
        self._setup(
            brain_dir,
            patterns=[pat],
            instances=[_make_instance("my_arch", "web", "sig_001")],
        )
        log_path = brain_dir / "ta_brain_interactions.jsonl"
        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   brain_dir / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   brain_dir / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1):
            query_brain(mode="infer", arch_name="my_arch", caller_type="mcp")

        entries = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
        assert len(entries) == 1
        assert entries[0]["caller_type"] == "mcp"
        assert entries[0]["query_mode"] == "infer"

    def test_miss_is_logged_with_had_match_false(self, brain_dir):
        self._setup(
            brain_dir,
            patterns=[],
            instances=[_make_instance("my_arch", "web", "sig_001")],
        )
        log_path = brain_dir / "ta_brain_interactions.jsonl"
        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   brain_dir / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   brain_dir / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1):
            result = query_brain(mode="infer", arch_name="my_arch")

        assert result["had_match"] is False
        entry = json.loads(log_path.read_text())
        assert entry["had_match"] is False

    def test_gaps_mode_returns_gap_list(self, brain_dir):
        gaps = [{"id": "GAP-001", "region": "arch_type:rare", "priority": 0.8,
                 "confidence_floor": 0.0, "generation_prompt": "...", "forced_gap": False}]
        self._setup(brain_dir, gaps=gaps)
        log_path = brain_dir / "ta_brain_interactions.jsonl"
        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   brain_dir / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   brain_dir / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1):
            result = query_brain(mode="gaps")

        assert result["mode"] == "gaps"
        assert result["gap_count"] == 1
        assert result["gaps"][0]["id"] == "GAP-001"

    def test_patterns_mode_returns_all_patterns(self, brain_dir):
        pats = [
            _make_pattern("BRAIN-001", "web", ["T1078"], ["mfa"]),
            _make_pattern("BRAIN-002", "iot", ["T1040"], ["segmentation"]),
        ]
        self._setup(brain_dir, patterns=pats)
        log_path = brain_dir / "ta_brain_interactions.jsonl"
        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   brain_dir / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   brain_dir / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1):
            result = query_brain(mode="patterns")

        assert result["pattern_count"] == 2

    def test_patterns_mode_filters_by_arch_type(self, brain_dir):
        pats = [
            _make_pattern("BRAIN-001", "web", ["T1078"], ["mfa"]),
            _make_pattern("BRAIN-002", "iot", ["T1040"], ["segmentation"]),
        ]
        self._setup(brain_dir, patterns=pats)
        log_path = brain_dir / "ta_brain_interactions.jsonl"
        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   brain_dir / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   brain_dir / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1):
            result = query_brain(mode="patterns", arch_type_filter="iot")

        assert result["pattern_count"] == 1
        assert result["patterns"][0]["id"] == "BRAIN-002"

    def test_invalid_mode_returns_error(self, brain_dir):
        self._setup(brain_dir)
        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   brain_dir / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   brain_dir / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH",
                   brain_dir / "ta_brain_interactions.jsonl"), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1):
            result = query_brain(mode="explain")  # not yet implemented

        assert "error" in result

    def test_error_when_brain_not_built(self, brain_dir):
        log_path = brain_dir / "ta_brain_interactions.jsonl"
        missing_path = brain_dir / "nonexistent_brain.json"
        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH", missing_path), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   brain_dir / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1):
            result = query_brain(mode="infer", arch_type="web")

        assert "error" in result

    def test_response_includes_pattern_version(self, brain_dir):
        pat = _make_pattern("BRAIN-001", "web", ["T1078"], ["mfa"])
        _write_brain(brain_dir, _make_brain(patterns=[pat], pattern_version=7))
        _write_instances(brain_dir, [_make_instance("arch1", "web", "sig1")])
        log_path = brain_dir / "ta_brain_interactions.jsonl"
        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   brain_dir / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   brain_dir / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1):
            result = query_brain(mode="infer", arch_name="arch1")

        assert result["pattern_version"] == 7


# ── E2E smoke — hold-out inference against real corpus ───────────────────────

class TestE2EHoldOutInference:
    """
    Stage 2 → 3 gate: query real corpus brain against hold-out architectures.
    Must predict ≥1 known missing control for each hold-out arch.
    Skipped if ta_brain.json or ta_brain_instances.jsonl are not built yet.
    """

    HOLD_OUT = ["21_agentic_ai_system", "03_aws_3tier", "20_data_pipeline"]

    def test_infer_predicts_missing_controls_for_hold_out_archs(self, tmp_path):
        report = Path(__file__).resolve().parents[2] / "report"
        brain_path = report / "ta_brain.json"
        instances_path = report / "ta_brain_instances.jsonl"

        if not brain_path.exists() or not instances_path.exists():
            pytest.skip("Brain not built — run: python3 -m chatbot.modules.ta_brain_builder")

        log_path = tmp_path / "interactions.jsonl"
        passed = []
        failed = []

        for arch_id in self.HOLD_OUT:
            arch_dir = report / arch_id
            gt_path = arch_dir / "ground_truth.json"
            if not gt_path.exists():
                continue

            gt = json.loads(gt_path.read_text())
            known_missing = set(
                gt.get("controls_missing")
                or gt.get("data", {}).get("controls_missing", [])
            )
            if not known_missing:
                continue

            with patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path), \
                 patch("chatbot.modules.ta_brain_query._brain_version", -1):
                result = query_brain(mode="infer", arch_name=arch_id)

            predicted = set(result.get("predictions", {}).get("missing_controls", []))
            overlap = known_missing & predicted

            if overlap:
                passed.append(arch_id)
            else:
                failed.append({
                    "arch": arch_id,
                    "known_missing": sorted(known_missing)[:5],
                    "predicted": sorted(predicted)[:5],
                })

        assert len(passed) >= 1, (
            f"E2E gate failed — no hold-out arch predicted ≥1 known missing control.\n"
            f"Failures: {failed}"
        )
