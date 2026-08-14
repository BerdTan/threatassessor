"""
Unit tests — Stage 7: TACO processor (coordinated feedback loop).

All tests are deterministic: no LLM calls, no network.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from chatbot.modules.ta_brain_taco_processor import (
    CALIB_PRIORITY_CONF_THRESHOLD,
    CALIB_PRIORITY_HIT_THRESHOLD,
    CONFIRM_BOOST_WEIGHT,
    apply_confirmation_boost,
    compute_calibration_priority,
    load_processor_state,
    reset_pattern_feedback_counts,
    run_taco_processor,
    save_processor_state,
)
from chatbot.modules.ta_brain_cache import reset_singleton as _reset_cache


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path):
    _reset_cache()
    with patch("chatbot.modules.ta_brain_cache.CACHE_PATH",
               tmp_path / "ta_brain_cache.json"):
        _reset_cache()
        yield
    _reset_cache()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pattern(pid, arch_type, corpus_conf=1.0, benchmark_conf=1.0,
                  confirmed=0, wrong=0, suspect=False):
    return {
        "id": pid,
        "corpus_confidence_base": corpus_conf,
        "trigger": {"arch_type": arch_type, "node_count_min": 3},
        "predicts": {
            "techniques": ["T1078"],
            "technique_frequencies": {"T1078": corpus_conf},
            "detect_rules": [],
            "aivss_floor": 0.3,
            "aivss_mean": 0.5,
            "common_missing_controls": ["mfa"],
            "control_frequencies": {"mfa": corpus_conf},
        },
        "corpus_confidence": corpus_conf,
        "benchmark_confidence": benchmark_conf,
        "evidence_count": 5,
        "real_evidence_count": 5,
        "evidence_arch_ids": [],
        "feedback_confirmed_count": confirmed,
        "feedback_wrong_count": wrong,
        "suspect": suspect,
        "trend": "stable",
        "remediation_template": {"priority_controls": [], "mmd_patch_stub": ""},
    }


def _make_brain(patterns=None, gaps=None):
    return {
        "version": 1, "pattern_version": 1, "corpus_size": 10,
        "train_size": 8, "hold_out": [],
        "patterns": patterns or [], "gaps": gaps or [],
    }


def _write_interactions(path, entries):
    with path.open("w") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _infer_entry(arch_type, had_match, feedback=None, cache_route="kg"):
    e = {
        "ts": "2026-08-12T10:00:00Z",
        "caller_type": "rest",
        "query_mode": "infer",
        "topology_signature": f"sig_{arch_type}",
        "arch_type": arch_type,
        "patterns_fired": [],
        "confidence_returned": 0.0,
        "had_match": had_match,
        "feedback": None,
        "cache_route": cache_route,
    }
    return e


def _feedback_entry(arch_type, feedback_val):
    return {
        "ts": "2026-08-12T10:01:00Z",
        "type": "feedback",
        "feedback": feedback_val,
        "topology_signature": f"sig_{arch_type}",
        "arch_type": arch_type,
        "query_mode": "infer",
        "reference_ts": "",
        "caller_type": "rest",
    }


# ── reset_pattern_feedback_counts ─────────────────────────────────────────────

class TestResetPatternFeedbackCounts:
    def test_zeros_out_feedback_counts(self):
        patterns = [_make_pattern("B-001", "web", confirmed=5, wrong=3, suspect=True)]
        reset = reset_pattern_feedback_counts(patterns)
        assert reset[0]["feedback_confirmed_count"] == 0
        assert reset[0]["feedback_wrong_count"] == 0
        assert reset[0]["suspect"] is False

    def test_does_not_mutate_original(self):
        p = _make_pattern("B-001", "web", confirmed=5, wrong=3)
        reset_pattern_feedback_counts([p])
        assert p["feedback_confirmed_count"] == 5

    def test_idempotency_after_reset(self):
        from chatbot.modules.ta_brain_confidence import run_confidence_decay

        p = _make_pattern("B-001", "web")
        p["corpus_confidence_base"] = p["corpus_confidence"]  # required for idempotency
        feedback = {
            "total_queries": 3, "total_feedback": 2,
            "by_pattern_sig": {"sig:web:infer": {"confirmed": 0, "wrong": 2, "partial": 0}},
        }
        brain = _make_brain([p])

        # Run twice with reset — should give same result
        brain1 = dict(brain)
        brain1["patterns"] = reset_pattern_feedback_counts(brain1["patterns"])
        r1 = run_confidence_decay(brain1, feedback)

        brain2 = {"patterns": [dict(r1["patterns"][0])]}
        brain2["patterns"] = reset_pattern_feedback_counts(brain2["patterns"])
        r2 = run_confidence_decay(brain2, feedback)

        assert r1["patterns"][0]["corpus_confidence"] == r2["patterns"][0]["corpus_confidence"]
        assert r1["patterns"][0]["feedback_wrong_count"] == r2["patterns"][0]["feedback_wrong_count"]


# ── apply_confirmation_boost ──────────────────────────────────────────────────

class TestApplyConfirmationBoost:
    def test_zero_confirmations_no_change(self):
        p = _make_pattern("B-001", "web", benchmark_conf=0.6)
        result = apply_confirmation_boost(p, 0, {})
        assert result == 0.6

    def test_confirmations_increase_benchmark_confidence(self):
        p = _make_pattern("B-001", "web", benchmark_conf=0.5)
        result = apply_confirmation_boost(p, 3, {})
        assert result > 0.5

    def test_boost_cannot_exceed_corpus_confidence(self):
        p = _make_pattern("B-001", "web", corpus_conf=0.7, benchmark_conf=0.65)
        result = apply_confirmation_boost(p, 100, {})
        assert result <= 0.7

    def test_boost_capped_at_conf_ceil(self):
        p = _make_pattern("B-001", "web", corpus_conf=1.0, benchmark_conf=0.99)
        result = apply_confirmation_boost(p, 100, {})
        assert result <= 1.0

    def test_diminishing_returns(self):
        p1 = _make_pattern("B-001", "web", benchmark_conf=0.5)
        p2 = _make_pattern("B-001", "web", benchmark_conf=0.5)
        b1 = apply_confirmation_boost(p1, 1, {})
        b10 = apply_confirmation_boost(p2, 10, {})
        # 10 confirmations → more boost, but not 10× more
        assert b10 > b1
        assert (b10 - 0.5) < 10 * (b1 - 0.5)


# ── compute_calibration_priority ──────────────────────────────────────────────

class TestComputeCalibrationPriority:
    def _write_cache(self, path, arch_type, hit_count):
        cache = {
            "entries": {
                f"sig_{arch_type}:{ arch_type}:infer": {
                    "topology_signature": f"sig_{arch_type}",
                    "arch_type": arch_type,
                    "query_mode": "infer",
                    "shape_counts": {},
                    "response": {},
                    "pattern_version": 1,
                    "hit_count": hit_count,
                    "last_hit_ts": None,
                    "last_confirmed_ts": None,
                    "created_ts": "2026-08-12T00:00:00Z",
                }
            }
        }
        path.write_text(json.dumps(cache))

    def test_flags_high_demand_low_confidence_patterns(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        self._write_cache(cache_path, "web",
                          hit_count=CALIB_PRIORITY_HIT_THRESHOLD + 1)
        p = _make_pattern("B-001", "web",
                          benchmark_conf=CALIB_PRIORITY_CONF_THRESHOLD - 0.1)
        result = compute_calibration_priority([p], {}, cache_path)
        assert len(result) == 1
        assert result[0]["pattern_id"] == "B-001"

    def test_does_not_flag_low_hit_count(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        self._write_cache(cache_path, "web",
                          hit_count=CALIB_PRIORITY_HIT_THRESHOLD - 1)
        p = _make_pattern("B-001", "web", benchmark_conf=0.3)
        result = compute_calibration_priority([p], {}, cache_path)
        assert len(result) == 0

    def test_does_not_flag_high_confidence_calibrated_patterns(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        self._write_cache(cache_path, "web",
                          hit_count=CALIB_PRIORITY_HIT_THRESHOLD + 5)
        p = _make_pattern("B-001", "web",
                          benchmark_conf=CALIB_PRIORITY_CONF_THRESHOLD + 0.1)
        # Provide benchmarks with samples_used > 0 so not flagged for zero-calibration
        benchmarks = {"brier_scores": {"B-001": {"samples_used": 3}}}
        result = compute_calibration_priority([p], benchmarks, cache_path)
        assert len(result) == 0

    def test_sorted_by_priority_score_descending(self, tmp_path):
        cache_path = tmp_path / "cache.json"
        cache = {"entries": {
            "sig_web:web:infer": {"arch_type": "web", "hit_count": 10,
                                   "topology_signature": "sig_web", "query_mode": "infer",
                                   "shape_counts": {}, "response": {}, "pattern_version": 1,
                                   "last_hit_ts": None, "last_confirmed_ts": None,
                                   "created_ts": ""},
            "sig_iot:iot:infer": {"arch_type": "iot", "hit_count": 5,
                                   "topology_signature": "sig_iot", "query_mode": "infer",
                                   "shape_counts": {}, "response": {}, "pattern_version": 1,
                                   "last_hit_ts": None, "last_confirmed_ts": None,
                                   "created_ts": ""},
        }}
        cache_path.write_text(json.dumps(cache))

        patterns = [
            _make_pattern("B-001", "web", benchmark_conf=0.2),
            _make_pattern("B-002", "iot", benchmark_conf=0.4),
        ]
        result = compute_calibration_priority(patterns, {}, cache_path)
        if len(result) >= 2:
            assert result[0]["priority_score"] >= result[1]["priority_score"]

    def test_missing_cache_returns_empty(self, tmp_path):
        p = _make_pattern("B-001", "web", benchmark_conf=0.3)
        result = compute_calibration_priority(
            [p], {}, tmp_path / "nonexistent_cache.json"
        )
        assert result == []


# ── load/save processor state ─────────────────────────────────────────────────

class TestProcessorState:
    def test_load_returns_defaults_when_missing(self, tmp_path):
        state = load_processor_state(tmp_path / "nonexistent.json")
        assert state["last_run_ts"] is None
        assert state["runs"] == 0

    def test_save_and_reload(self, tmp_path):
        state_path = tmp_path / "state.json"
        state = {"last_run_ts": "2026-08-12T10:00:00Z", "runs": 3,
                 "total_interactions_processed": 15}
        save_processor_state(state, state_path)
        loaded = load_processor_state(state_path)
        assert loaded["runs"] == 3
        assert loaded["total_interactions_processed"] == 15


# ── run_taco_processor ────────────────────────────────────────────────────────

class TestRunTacoProcessor:
    def _setup(self, tmp_path, patterns=None, interactions=None, instances=None):
        brain_path = tmp_path / "ta_brain.json"
        instances_path = tmp_path / "ta_brain_instances.jsonl"
        interactions_path = tmp_path / "ta_brain_interactions.jsonl"
        benchmarks_path = tmp_path / "ta_brain_benchmarks.json"
        state_path = tmp_path / "state.json"
        cache_path = tmp_path / "ta_brain_cache.json"

        brain = _make_brain(patterns or [_make_pattern("B-001", "web")])
        brain_path.write_text(json.dumps(brain))

        if instances:
            with instances_path.open("w") as f:
                for i in instances:
                    f.write(json.dumps(i) + "\n")
        else:
            instances_path.write_text("")

        if interactions:
            _write_interactions(interactions_path, interactions)
        else:
            interactions_path.write_text("")

        return brain_path, instances_path, interactions_path, benchmarks_path, state_path, cache_path

    def test_returns_summary_dict(self, tmp_path):
        brain_path, inst, inter, bm, state, cache = self._setup(tmp_path)
        result = run_taco_processor(brain_path, bm, inst, inter, cache, state)
        for field in ("patterns", "suspect_patterns", "avg_benchmark_confidence",
                      "gaps_total", "run_ts", "processor_runs_total"):
            assert field in result

    def test_increments_run_counter(self, tmp_path):
        brain_path, inst, inter, bm, state, cache = self._setup(tmp_path)
        run_taco_processor(brain_path, bm, inst, inter, cache, state)
        run_taco_processor(brain_path, bm, inst, inter, cache, state)
        loaded_state = load_processor_state(state)
        assert loaded_state["runs"] == 2

    def test_idempotent_with_same_log(self, tmp_path):
        """Running twice with same log gives same brain state."""
        entries = [
            _feedback_entry("web", "wrong"),
            _feedback_entry("web", "wrong"),
        ]
        brain_path, inst, inter, bm, state, cache = self._setup(
            tmp_path, interactions=entries
        )
        run_taco_processor(brain_path, bm, inst, inter, cache, state)
        brain_after_1 = json.loads(brain_path.read_text())

        run_taco_processor(brain_path, bm, inst, inter, cache, state)
        brain_after_2 = json.loads(brain_path.read_text())

        p1 = brain_after_1["patterns"][0]
        p2 = brain_after_2["patterns"][0]
        assert p1["corpus_confidence"] == p2["corpus_confidence"]
        assert p1["feedback_wrong_count"] == p2["feedback_wrong_count"]

    def test_decay_reduces_confidence_on_wrong_feedback(self, tmp_path):
        entries = [_feedback_entry("web", "wrong")] * 3
        brain_path, inst, inter, bm, state, cache = self._setup(
            tmp_path, interactions=entries
        )
        run_taco_processor(brain_path, bm, inst, inter, cache, state)
        brain = json.loads(brain_path.read_text())
        p = brain["patterns"][0]
        assert p["corpus_confidence"] < 1.0

    def test_confirmed_feedback_boosts_benchmark_confidence(self, tmp_path):
        # Start with low benchmark_confidence
        patterns = [_make_pattern("B-001", "web", benchmark_conf=0.5)]
        entries = [_feedback_entry("web", "confirmed")] * 5
        brain_path, inst, inter, bm, state, cache = self._setup(
            tmp_path, patterns=patterns, interactions=entries
        )
        run_taco_processor(brain_path, bm, inst, inter, cache, state)
        brain = json.loads(brain_path.read_text())
        p = brain["patterns"][0]
        assert p["benchmark_confidence"] > 0.5

    def test_writes_taco_processor_ts_to_brain(self, tmp_path):
        brain_path, inst, inter, bm, state, cache = self._setup(tmp_path)
        run_taco_processor(brain_path, bm, inst, inter, cache, state)
        brain = json.loads(brain_path.read_text())
        assert "taco_processor_ts" in brain

    def test_raises_when_brain_missing(self, tmp_path):
        with pytest.raises(ValueError):
            run_taco_processor(
                tmp_path / "nonexistent.json",
                tmp_path / "bm.json",
                tmp_path / "inst.jsonl",
                tmp_path / "inter.jsonl",
                tmp_path / "cache.json",
                tmp_path / "state.json",
            )

    def test_forced_gaps_preserved(self, tmp_path):
        forced = {
            "id": "GAP-F001", "region": "arch_type:rare",
            "type": "benchmark_divergence", "forced_gap": True,
            "priority": 0.9, "confidence_floor": 0.0,
            "generation_prompt": "forced", "demand_weight": 0.0,
            "miss_count": 0, "variant_count": 0, "total_queries": 0,
        }
        patterns = [_make_pattern("B-001", "web")]
        brain = _make_brain(patterns, gaps=[forced])
        brain_path = tmp_path / "ta_brain.json"
        brain_path.write_text(json.dumps(brain))

        inst = tmp_path / "inst.jsonl"; inst.write_text("")
        inter = tmp_path / "inter.jsonl"; inter.write_text("")
        bm = tmp_path / "bm.json"
        state = tmp_path / "state.json"
        cache = tmp_path / "cache.json"

        run_taco_processor(brain_path, bm, inst, inter, cache, state)
        result_brain = json.loads(brain_path.read_text())
        forced_gaps = [g for g in result_brain["gaps"] if g.get("forced_gap")]
        assert len(forced_gaps) >= 1

    def test_suspect_flag_set_on_high_wrong_rate(self, tmp_path):
        from chatbot.modules.ta_brain_taco_processor import CALIB_PRIORITY_CONF_THRESHOLD
        entries = [_feedback_entry("web", "wrong")] * 5
        brain_path, inst, inter, bm, state, cache = self._setup(
            tmp_path, interactions=entries
        )
        run_taco_processor(brain_path, bm, inst, inter, cache, state)
        brain = json.loads(brain_path.read_text())
        p = brain["patterns"][0]
        assert p.get("suspect") is True


# ── Live corpus run ───────────────────────────────────────────────────────────

class TestLiveCorpusProcessor:
    def test_processor_runs_on_real_corpus(self, tmp_path):
        brain_path = Path("report/ta_brain.json")
        if not brain_path.exists():
            pytest.skip("Brain not built")

        state_path = tmp_path / "state.json"
        result = run_taco_processor(
            brain_path=brain_path,
            state_path=state_path,
        )
        assert result["patterns"] >= 1
        assert result["processor_runs_total"] == 1
        loaded = load_processor_state(state_path)
        assert loaded["runs"] == 1
