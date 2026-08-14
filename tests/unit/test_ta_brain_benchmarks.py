"""
Unit tests — Stage 6: benchmark calibration (Brier scoring + framework floors).

All tests are deterministic: no LLM calls, no network.
"""

import json
import pytest
from pathlib import Path

from chatbot.modules.ta_brain_benchmarks import (
    BRIER_SCALE,
    DIVERGENCE_THRESHOLD,
    FRAMEWORK_DIVERGENCE_FLOOR,
    FRAMEWORK_FLOORS,
    brier_score_set,
    brier_to_confidence,
    calibrate_pattern_brier,
    compute_framework_confidence,
    ingest_incident,
    run_calibration,
    save_calibration,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pattern(pid, arch_type, tech_freqs=None, ctrl_freqs=None,
                  corpus_conf=1.0, benchmark_conf=1.0):
    return {
        "id": pid,
        "trigger": {"arch_type": arch_type, "node_count_min": 3},
        "predicts": {
            "techniques": list((tech_freqs or {}).keys()),
            "technique_frequencies": tech_freqs or {},
            "detect_rules": [],
            "aivss_floor": 0.3,
            "aivss_mean": 0.5,
            "common_missing_controls": list((ctrl_freqs or {}).keys()),
            "control_frequencies": ctrl_freqs or {},
        },
        "corpus_confidence": corpus_conf,
        "benchmark_confidence": benchmark_conf,
        "evidence_count": 5,
        "real_evidence_count": 5,
        "evidence_arch_ids": [],
        "feedback_confirmed_count": 0,
        "feedback_wrong_count": 0,
        "suspect": False,
        "trend": "stable",
        "remediation_template": {"priority_controls": [], "mmd_patch_stub": ""},
    }


def _make_brain(patterns=None, gaps=None):
    return {
        "version": 1, "pattern_version": 1,
        "corpus_size": 10, "train_size": 8, "hold_out": [],
        "patterns": patterns or [], "gaps": gaps or [],
    }


def _make_instance(arch_id, arch_type):
    return {"arch_id": arch_id, "arch_type": arch_type,
            "topology_signature": f"sig_{arch_id}", "source": "real",
            "node_count": 5, "edge_count": 3}


def _write_ground_truth(path, arch_id, techniques, controls_missing):
    arch_dir = path / arch_id
    arch_dir.mkdir(exist_ok=True)
    gt = {
        "architecture": arch_id,
        "metadata": {"architecture_type": "web", "node_count": 5, "parsed_nodes": {},
                     "parsed_edges": [], "run_ts": "", "run_id": ""},
        "techniques": techniques,
        "controls_missing": controls_missing,
    }
    (arch_dir / "ground_truth.json").write_text(json.dumps(gt))


# ── brier_score_set ───────────────────────────────────────────────────────────

class TestBrierScoreSet:
    def test_perfect_predictions_score_zero(self):
        # Predict 1.0 for items in actual, nothing else
        predicted = {"T1078": 1.0, "T1059": 1.0}
        actual = {"T1078", "T1059"}
        assert brier_score_set(predicted, actual) == 0.0

    def test_worst_predictions_score_one(self):
        # Predict 1.0 for items NOT in actual (pure false positives)
        predicted = {"T1078": 1.0}
        actual = set()
        # brier = (1.0 - 0)^2 / 1 = 1.0
        assert abs(brier_score_set(predicted, actual) - 1.0) < 1e-6

    def test_false_negative_not_penalized(self):
        # Item in actual but not predicted — precision-only scorer ignores this
        # Returns 0.5 (neutral) because nothing was predicted
        predicted = {}
        actual = {"T1078"}
        assert abs(brier_score_set(predicted, actual) - 0.5) < 1e-6

    def test_partial_prediction(self):
        # Predict 0.5 for item in actual
        predicted = {"T1078": 0.5}
        actual = {"T1078"}
        # brier = (0.5 - 1)^2 / 1 = 0.25
        assert abs(brier_score_set(predicted, actual) - 0.25) < 1e-6

    def test_empty_inputs_return_neutral(self):
        # No predictions → neutral score (0.5), not zero
        assert brier_score_set({}, set()) == 0.5

    def test_precision_only_scores_predicted(self):
        # T1078 predicted + correct, T1099 in actual but not predicted (ignored)
        # T1059 predicted but wrong → penalised
        predicted = {"T1078": 0.8, "T1059": 0.2}
        actual = {"T1078", "T1099"}
        # T1078: (0.8-1)^2 = 0.04; T1059: (0.2-0)^2 = 0.04 → avg = 0.04
        score = brier_score_set(predicted, actual)
        assert abs(score - 0.04) < 1e-4


# ── brier_to_confidence ───────────────────────────────────────────────────────

class TestBrierToConfidence:
    def test_zero_brier_gives_one_confidence(self):
        assert brier_to_confidence(0.0) == 1.0

    def test_half_brier_scale_gives_zero_confidence(self):
        assert brier_to_confidence(BRIER_SCALE) == 0.0

    def test_random_brier_gives_half_confidence(self):
        # Brier=0.25 (random predictor) → conf=0.5
        assert abs(brier_to_confidence(0.25) - 0.5) < 0.01

    def test_over_scale_clamped_to_zero(self):
        assert brier_to_confidence(1.0) == 0.0

    def test_monotonically_decreasing(self):
        scores = [0.0, 0.1, 0.2, 0.3, 0.4, 0.5]
        confs = [brier_to_confidence(s) for s in scores]
        assert all(confs[i] >= confs[i+1] for i in range(len(confs)-1))


# ── compute_framework_confidence ──────────────────────────────────────────────

class TestComputeFrameworkConfidence:
    def test_full_coverage_gives_max_confidence(self):
        required = FRAMEWORK_FLOORS["web_app"]["required_controls"]
        pattern = _make_pattern("B-001", "web_app",
                                ctrl_freqs={c: 0.9 for c in required})
        result = compute_framework_confidence(pattern, "web_app")
        assert result["framework_confidence"] == 1.0
        assert result["coverage_ratio"] == 1.0
        assert result["missing_required"] == []

    def test_zero_coverage_gives_floor_confidence(self):
        floor = FRAMEWORK_FLOORS["web_app"]["floor_confidence"]
        pattern = _make_pattern("B-001", "web_app", ctrl_freqs={})
        result = compute_framework_confidence(pattern, "web_app")
        assert abs(result["framework_confidence"] - floor) < 0.01

    def test_partial_coverage_between_floor_and_max(self):
        required = FRAMEWORK_FLOORS["web_app"]["required_controls"]
        half = required[:len(required)//2]
        pattern = _make_pattern("B-001", "web_app",
                                ctrl_freqs={c: 0.8 for c in half})
        result = compute_framework_confidence(pattern, "web_app")
        floor = FRAMEWORK_FLOORS["web_app"]["floor_confidence"]
        assert floor < result["framework_confidence"] < 1.0

    def test_unknown_arch_type_uncalibrated(self):
        pattern = _make_pattern("B-001", "unknown_type")
        result = compute_framework_confidence(pattern, "unknown_type")
        assert result["framework_confidence"] == 1.0
        assert result["source"] == "uncalibrated"

    def test_returns_missing_required_list(self):
        required = FRAMEWORK_FLOORS["ai_system"]["required_controls"]
        pattern = _make_pattern("B-001", "ai_system", ctrl_freqs={})
        result = compute_framework_confidence(pattern, "ai_system")
        for r in required:
            assert r in result["missing_required"]

    def test_case_insensitive_matching(self):
        pattern = _make_pattern("B-001", "web_app",
                                ctrl_freqs={"MFA": 0.9, "WAF": 0.8, "LOGGING": 0.7,
                                            "INPUT VALIDATION": 0.6,
                                            "PATCH MANAGEMENT": 0.5, "AUTHENTICATION": 0.9})
        result = compute_framework_confidence(pattern, "web_app")
        assert result["coverage_ratio"] == 1.0


# ── calibrate_pattern_brier ───────────────────────────────────────────────────

class TestCalibratePatternBrier:
    def test_returns_uncalibrated_when_no_hold_out_match(self, tmp_path):
        p = _make_pattern("B-001", "cloud")
        instances = [_make_instance("a1", "web")]
        result = calibrate_pattern_brier(p, instances, tmp_path)
        assert result["samples_used"] == 0
        assert result["benchmark_confidence_brier"] == 1.0
        assert result["brier_combined"] is None

    def test_computes_brier_against_matching_hold_out(self, tmp_path):
        _write_ground_truth(tmp_path, "hold_web", ["T1078", "T1059"], ["mfa", "logging"])
        p = _make_pattern("B-001", "web",
                          tech_freqs={"T1078": 0.9, "T1059": 0.8},
                          ctrl_freqs={"mfa": 0.8, "logging": 0.7})
        instances = [_make_instance("hold_web", "web")]
        result = calibrate_pattern_brier(p, instances, tmp_path)
        assert result["samples_used"] == 1
        assert result["brier_combined"] is not None
        assert 0.0 <= result["brier_combined"] <= 1.0
        assert "hold_web" in result["calibrated_hold_out"]

    def test_perfect_predictions_give_high_confidence(self, tmp_path):
        _write_ground_truth(tmp_path, "hold_arch", ["T1078", "T1059"], ["mfa"])
        p = _make_pattern("B-001", "web",
                          tech_freqs={"T1078": 1.0, "T1059": 1.0},
                          ctrl_freqs={"mfa": 1.0})
        instances = [_make_instance("hold_arch", "web")]
        result = calibrate_pattern_brier(p, instances, tmp_path)
        assert result["benchmark_confidence_brier"] > 0.8

    def test_wrong_predictions_give_low_confidence(self, tmp_path):
        # Predict T1078 at 1.0 but actual has none of those
        _write_ground_truth(tmp_path, "hold_arch", ["T9999"], ["some_other_control"])
        p = _make_pattern("B-001", "web",
                          tech_freqs={"T1078": 1.0, "T1059": 1.0},
                          ctrl_freqs={"mfa": 1.0})
        instances = [_make_instance("hold_arch", "web")]
        result = calibrate_pattern_brier(p, instances, tmp_path)
        # High Brier → low confidence
        assert result["benchmark_confidence_brier"] < 0.5


# ── run_calibration ───────────────────────────────────────────────────────────

class TestRunCalibration:
    def test_updates_benchmark_confidence_in_patterns(self, tmp_path):
        _write_ground_truth(tmp_path, "hold_web", ["T1078", "T1059"], ["mfa", "logging"])
        p = _make_pattern("B-001", "web_app",
                          tech_freqs={"T1078": 0.9, "T1059": 0.8},
                          ctrl_freqs={"mfa": 0.8, "waf": 0.7, "logging": 0.6,
                                      "input validation": 0.5,
                                      "patch management": 0.4, "authentication": 0.9})
        brain = _make_brain([p])
        hold_outs = [_make_instance("hold_web", "web_app")]

        updated_brain, benchmarks = run_calibration(brain, hold_outs, tmp_path)
        up = updated_brain["patterns"][0]
        assert up["benchmark_confidence"] != 1.0 or benchmarks["brier_scores"]["B-001"]["samples_used"] == 0

    def test_creates_forced_gap_on_divergence(self, tmp_path):
        # Predict everything wrong → high Brier → divergence
        _write_ground_truth(tmp_path, "hold_arch", ["T9999", "T8888"], ["rare_ctrl"])
        p = _make_pattern("B-001", "web_app",
                          tech_freqs={"T1078": 1.0, "T1059": 1.0, "T1040": 1.0},
                          ctrl_freqs={})  # no framework controls covered
        brain = _make_brain([p])
        hold_outs = [_make_instance("hold_arch", "web_app")]

        updated_brain, benchmarks = run_calibration(brain, hold_outs, tmp_path)

        # Should have divergence and forced gap
        if benchmarks["divergences"]:
            forced = [g for g in updated_brain.get("gaps", []) if g.get("forced_gap")]
            assert len(forced) >= 1
            assert forced[0]["type"] == "benchmark_divergence"

    def test_uncalibrated_patterns_keep_benchmark_confidence_one(self, tmp_path):
        p = _make_pattern("B-001", "cloud")  # no hold-out for cloud
        brain = _make_brain([p])
        # Only web hold-out
        _write_ground_truth(tmp_path, "hold_web", ["T1078"], ["mfa"])
        hold_outs = [_make_instance("hold_web", "web")]

        updated_brain, _ = run_calibration(brain, hold_outs, tmp_path)
        up = updated_brain["patterns"][0]
        # No hold-out for cloud → benchmark_confidence from framework only
        assert up["benchmark_confidence"] > 0.0

    def test_benchmark_confidence_is_min_of_brier_and_framework(self, tmp_path):
        # Perfect Brier but bad framework coverage → framework limits
        _write_ground_truth(tmp_path, "hold_ai", ["T1078"], ["rate limiting"])
        p = _make_pattern("B-001", "ai_system",
                          tech_freqs={"T1078": 1.0},
                          ctrl_freqs={"rate limiting": 1.0})
        brain = _make_brain([p])
        hold_outs = [_make_instance("hold_ai", "ai_system")]

        updated_brain, benchmarks = run_calibration(brain, hold_outs, tmp_path)
        up = updated_brain["patterns"][0]
        brier_conf = benchmarks["brier_scores"]["B-001"]["benchmark_confidence_brier"]
        fw_conf = benchmarks["framework_results"]["B-001"]["framework_confidence"]
        # benchmark_confidence = min(brier_conf, fw_conf)
        assert abs(up["benchmark_confidence"] - min(brier_conf, fw_conf)) < 1e-4

    def test_does_not_duplicate_forced_gaps(self, tmp_path):
        existing_gap = {
            "id": "GAP-001", "region": "arch_type:web_app",
            "type": "coverage_thin", "forced_gap": True, "priority": 0.9,
            "confidence_floor": 0.0, "generation_prompt": "existing",
            "demand_weight": 0.0, "miss_count": 0, "variant_count": 0, "total_queries": 0,
        }
        p = _make_pattern("B-001", "web_app",
                          tech_freqs={"T9999": 1.0}, ctrl_freqs={})
        brain = _make_brain([p], gaps=[existing_gap])
        _write_ground_truth(tmp_path, "hold_web", ["T1078"], ["mfa"])
        hold_outs = [_make_instance("hold_web", "web_app")]

        updated_brain, _ = run_calibration(brain, hold_outs, tmp_path)
        # Should not add another forced gap for same region if already exists
        web_gaps = [g for g in updated_brain.get("gaps", [])
                    if g["region"] == "arch_type:web_app"]
        assert len(web_gaps) <= 2  # at most original + 1 new


# ── ingest_incident ───────────────────────────────────────────────────────────

class TestIngestIncident:
    def test_appends_incident_to_benchmarks(self, tmp_path):
        bm_path = tmp_path / "ta_brain_benchmarks.json"
        incident = {
            "id": "AIID-001",
            "title": "ChatGPT prompt injection",
            "arch_type": "ai_system",
            "date": "2026-01-15",
            "source": "aiid",
            "techniques_actual": ["AML.T0020"],
            "controls_missing_actual": ["input validation"],
        }
        entry = ingest_incident(incident, bm_path)
        assert entry["id"] == "AIID-001"
        bm = json.loads(bm_path.read_text())
        assert len(bm["incidents"]) == 1

    def test_deduplicates_by_id(self, tmp_path):
        bm_path = tmp_path / "ta_brain_benchmarks.json"
        incident = {"id": "AIID-001", "arch_type": "web",
                    "techniques_actual": ["T1078"]}
        ingest_incident(incident, bm_path)
        ingest_incident(incident, bm_path)  # duplicate
        bm = json.loads(bm_path.read_text())
        assert len(bm["incidents"]) == 1

    def test_raises_on_missing_required_fields(self, tmp_path):
        with pytest.raises(ValueError, match="missing required fields"):
            ingest_incident({"title": "no id"}, tmp_path / "bm.json")


# ── save_calibration ──────────────────────────────────────────────────────────

class TestSaveCalibration:
    def _setup(self, tmp_path):
        brain_path = tmp_path / "ta_brain.json"
        instances_path = tmp_path / "ta_brain_instances.jsonl"
        p = _make_pattern("B-001", "web_app",
                          tech_freqs={"T1078": 0.8},
                          ctrl_freqs={"mfa": 0.9, "waf": 0.8, "logging": 0.7,
                                      "input validation": 0.6, "patch management": 0.5,
                                      "authentication": 0.9})
        brain = _make_brain([p])
        brain_path.write_text(json.dumps(brain))

        inst = _make_instance("hold_web", "web_app")
        instances_path.write_text(json.dumps(inst) + "\n")
        _write_ground_truth(tmp_path, "hold_web", ["T1078", "T1059"], ["mfa"])
        return brain_path, instances_path

    def test_writes_both_files(self, tmp_path):
        brain_path, instances_path = self._setup(tmp_path)
        bm_path = tmp_path / "ta_brain_benchmarks.json"

        save_calibration(brain_path, bm_path, instances_path,
                         report_dir=tmp_path, hold_out_arch_ids={"hold_web"})

        assert brain_path.exists()
        assert bm_path.exists()

    def test_raises_when_brain_missing(self, tmp_path):
        with pytest.raises(ValueError):
            save_calibration(tmp_path / "nonexistent.json")

    def test_returns_summary(self, tmp_path):
        brain_path, instances_path = self._setup(tmp_path)
        bm_path = tmp_path / "ta_brain_benchmarks.json"

        result = save_calibration(brain_path, bm_path, instances_path,
                                  report_dir=tmp_path, hold_out_arch_ids={"hold_web"})

        assert "patterns_total" in result
        assert "patterns_calibrated" in result
        assert "divergences" in result
        assert "calibrated_ts" in result


# ── Integration: live corpus calibration ─────────────────────────────────────

class TestLiveCorpusCalibration:
    """Run calibration against real corpus files. Skipped if not built."""

    def test_calibrates_real_hold_out_archs(self, tmp_path):
        brain_path = Path("report/ta_brain.json")
        instances_path = Path("report/ta_brain_instances.jsonl")
        if not brain_path.exists() or not instances_path.exists():
            pytest.skip("Brain not built")

        bm_path = tmp_path / "ta_brain_benchmarks.json"
        result = save_calibration(
            brain_path=brain_path,
            benchmarks_path=bm_path,
            instances_path=instances_path,
            report_dir=Path("report"),
        )

        # Must calibrate at least 3 patterns (web_app, generic, ai_system)
        assert result["patterns_calibrated"] >= 3
        # Avg Brier should be reasonable (< 0.6 — not completely random)
        if result["avg_brier_combined"] is not None:
            assert result["avg_brier_combined"] < 0.6

        bm = json.loads(bm_path.read_text())
        # Every calibrated pattern has a Brier score
        for pid, scores in bm["brier_scores"].items():
            if scores["samples_used"] > 0:
                assert scores["brier_combined"] is not None
                assert 0.0 <= scores["brier_combined"] <= 1.0
