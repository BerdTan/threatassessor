"""
Unit tests — Stage 4: confidence decay + counter-evidence logic.

All tests are deterministic: no LLM calls, no network.
"""

import json
import math
import pytest
from pathlib import Path
from unittest.mock import patch

from chatbot.modules.ta_brain_confidence import (
    CONF_CEIL,
    CONF_FLOOR,
    DELTA_NEGATIVE,
    DELTA_POSITIVE_BASE,
    SUSPECT_MIN_WRONG,
    SUSPECT_WRONG_RATE,
    apply_feedback_to_pattern,
    delta_positive,
    run_confidence_decay,
    save_confidence_decay,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_pattern(pid, arch_type, corpus_conf=1.0, evidence=5,
                  confirmed=0, wrong=0, suspect=False):
    return {
        "id": pid,
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
        "benchmark_confidence": 1.0,
        "evidence_count": evidence,
        "real_evidence_count": evidence,
        "evidence_arch_ids": [f"arch_{i}" for i in range(evidence)],
        "feedback_confirmed_count": confirmed,
        "feedback_wrong_count": wrong,
        "suspect": suspect,
        "trend": "stable",
        "remediation_template": {"priority_controls": ["mfa"], "mmd_patch_stub": ""},
    }


def _make_brain(patterns=None):
    return {
        "version": 1,
        "pattern_version": 1,
        "built_ts": "2026-08-12T00:00:00Z",
        "corpus_size": 10,
        "train_size": 8,
        "hold_out": [],
        "patterns": patterns or [],
        "gaps": [],
    }


def _make_feedback_summary(by_sig=None):
    return {
        "total_queries": 5,
        "total_feedback": len(by_sig or {}),
        "by_pattern_sig": by_sig or {},
    }


# ── delta_positive ────────────────────────────────────────────────────────────

class TestDeltaPositive:
    def test_decreases_with_more_evidence(self):
        d1 = delta_positive(1)
        d5 = delta_positive(5)
        d10 = delta_positive(10)
        assert d1 > d5 > d10

    def test_base_case_evidence_one(self):
        assert abs(delta_positive(1) - DELTA_POSITIVE_BASE) < 1e-6

    def test_matches_formula(self):
        for ev in [1, 4, 9, 16]:
            expected = round(DELTA_POSITIVE_BASE / math.sqrt(ev), 6)
            assert abs(delta_positive(ev) - expected) < 1e-8


# ── apply_feedback_to_pattern ─────────────────────────────────────────────────

class TestApplyFeedbackToPattern:
    def test_confirmed_raises_corpus_confidence(self):
        p = _make_pattern("B-001", "web", corpus_conf=0.7, evidence=4)
        updated = apply_feedback_to_pattern(p, confirmed_count=1, wrong_count=0)
        assert updated["corpus_confidence"] > 0.7

    def test_wrong_lowers_corpus_confidence(self):
        p = _make_pattern("B-001", "web", corpus_conf=0.7, evidence=4)
        updated = apply_feedback_to_pattern(p, confirmed_count=0, wrong_count=1)
        assert updated["corpus_confidence"] < 0.7

    def test_confidence_clamped_to_ceil(self):
        p = _make_pattern("B-001", "web", corpus_conf=0.99, evidence=1)
        updated = apply_feedback_to_pattern(p, confirmed_count=10, wrong_count=0)
        assert updated["corpus_confidence"] <= CONF_CEIL

    def test_confidence_clamped_to_floor(self):
        p = _make_pattern("B-001", "web", corpus_conf=0.1, evidence=1)
        updated = apply_feedback_to_pattern(p, confirmed_count=0, wrong_count=100)
        assert updated["corpus_confidence"] >= CONF_FLOOR

    def test_accumulates_counts(self):
        p = _make_pattern("B-001", "web", confirmed=2, wrong=1)
        updated = apply_feedback_to_pattern(p, confirmed_count=3, wrong_count=1)
        assert updated["feedback_confirmed_count"] == 5
        assert updated["feedback_wrong_count"] == 2

    def test_suspect_flagged_at_threshold(self):
        p = _make_pattern("B-001", "web")
        # 3 wrong, 0 confirmed → wrong_rate=1.0 → suspect
        updated = apply_feedback_to_pattern(p, confirmed_count=0, wrong_count=SUSPECT_MIN_WRONG)
        assert updated["suspect"] is True

    def test_suspect_not_flagged_below_min_wrong(self):
        p = _make_pattern("B-001", "web")
        # 2 wrong (< SUSPECT_MIN_WRONG=3) → not suspect
        updated = apply_feedback_to_pattern(p, confirmed_count=0, wrong_count=2)
        assert updated["suspect"] is False

    def test_suspect_not_flagged_when_wrong_rate_low(self):
        p = _make_pattern("B-001", "web")
        # 3 wrong but 10 confirmed → rate = 3/13 ≈ 0.23 < 0.5 → not suspect
        updated = apply_feedback_to_pattern(p, confirmed_count=10, wrong_count=3)
        assert updated["suspect"] is False

    def test_is_pure_function_does_not_mutate_input(self):
        p = _make_pattern("B-001", "web", corpus_conf=0.8)
        original_conf = p["corpus_confidence"]
        apply_feedback_to_pattern(p, confirmed_count=2, wrong_count=1)
        assert p["corpus_confidence"] == original_conf

    def test_zero_feedback_preserves_confidence(self):
        p = _make_pattern("B-001", "web", corpus_conf=0.75)
        updated = apply_feedback_to_pattern(p, confirmed_count=0, wrong_count=0)
        assert updated["corpus_confidence"] == 0.75

    def test_delta_positive_is_evidence_scaled(self):
        p_low = _make_pattern("B-001", "web", corpus_conf=0.5, evidence=1)
        p_high = _make_pattern("B-002", "web", corpus_conf=0.5, evidence=100)
        updated_low = apply_feedback_to_pattern(p_low, 1, 0)
        updated_high = apply_feedback_to_pattern(p_high, 1, 0)
        # Low evidence → bigger boost per confirmation
        delta_low = updated_low["corpus_confidence"] - 0.5
        delta_high = updated_high["corpus_confidence"] - 0.5
        assert delta_low > delta_high


# ── run_confidence_decay ──────────────────────────────────────────────────────

class TestRunConfidenceDecay:
    def test_updates_matching_arch_type_patterns(self):
        patterns = [_make_pattern("B-001", "web")]
        brain = _make_brain(patterns)
        feedback = _make_feedback_summary({
            "sig_a:web:infer": {"confirmed": 2, "wrong": 0, "partial": 0}
        })
        updated = run_confidence_decay(brain, feedback)
        p = next(p for p in updated["patterns"] if p["id"] == "B-001")
        assert p["corpus_confidence"] > 1.0 - 1e-6  # started at 1.0, boosted → still ≤ 1.0
        assert p["feedback_confirmed_count"] == 2

    def test_does_not_affect_non_matching_arch_type(self):
        patterns = [
            _make_pattern("B-001", "web"),
            _make_pattern("B-002", "iot"),
        ]
        brain = _make_brain(patterns)
        feedback = _make_feedback_summary({
            "sig_a:web:infer": {"confirmed": 0, "wrong": 3, "partial": 0}
        })
        updated = run_confidence_decay(brain, feedback)
        iot_p = next(p for p in updated["patterns"] if p["id"] == "B-002")
        assert iot_p["corpus_confidence"] == 1.0  # unchanged

    def test_aggregates_multiple_sigs_of_same_arch_type(self):
        patterns = [_make_pattern("B-001", "web", corpus_conf=0.9, evidence=5)]
        brain = _make_brain(patterns)
        # Two different topology_sigs both for web, both wrong
        feedback = _make_feedback_summary({
            "sig_a:web:infer": {"confirmed": 0, "wrong": 1, "partial": 0},
            "sig_b:web:infer": {"confirmed": 0, "wrong": 1, "partial": 0},
        })
        updated = run_confidence_decay(brain, feedback)
        p = updated["patterns"][0]
        # 2 wrong total → decay of 2 * DELTA_NEGATIVE
        expected = round(max(CONF_FLOOR, 0.9 - 2 * DELTA_NEGATIVE), 6)
        assert abs(p["corpus_confidence"] - expected) < 1e-4

    def test_ignores_non_infer_mode_feedback(self):
        patterns = [_make_pattern("B-001", "web")]
        brain = _make_brain(patterns)
        feedback = _make_feedback_summary({
            "sig_a:web:patterns": {"confirmed": 0, "wrong": 5, "partial": 0}
        })
        updated = run_confidence_decay(brain, feedback)
        p = updated["patterns"][0]
        assert p["corpus_confidence"] == 1.0  # patterns mode ignored

    def test_adds_decay_metadata_to_brain(self):
        brain = _make_brain([_make_pattern("B-001", "web")])
        updated = run_confidence_decay(brain, _make_feedback_summary())
        assert "feedback_decay_ts" in updated
        assert "feedback_total_confirmed" in updated
        assert "feedback_total_wrong" in updated

    def test_initialises_missing_feedback_fields(self):
        # Pattern without feedback fields (pre-Stage 4 brain)
        p = {
            "id": "B-OLD", "trigger": {"arch_type": "web"},
            "corpus_confidence": 0.8, "evidence_count": 3,
            "benchmark_confidence": 1.0,
        }
        brain = _make_brain([p])
        updated = run_confidence_decay(brain, _make_feedback_summary())
        up = updated["patterns"][0]
        assert "feedback_confirmed_count" in up
        assert "feedback_wrong_count" in up
        assert "suspect" in up

    def test_empty_feedback_summary_leaves_confidence_unchanged(self):
        p = _make_pattern("B-001", "web", corpus_conf=0.75)
        brain = _make_brain([p])
        updated = run_confidence_decay(brain, _make_feedback_summary())
        assert updated["patterns"][0]["corpus_confidence"] == 0.75

    def test_is_pure_function_does_not_mutate_input(self):
        patterns = [_make_pattern("B-001", "web", corpus_conf=0.8)]
        brain = _make_brain(patterns)
        feedback = _make_feedback_summary({
            "sig_a:web:infer": {"confirmed": 0, "wrong": 2, "partial": 0}
        })
        run_confidence_decay(brain, feedback)
        # Original brain unchanged
        assert brain["patterns"][0]["corpus_confidence"] == 0.8


# ── save_confidence_decay ─────────────────────────────────────────────────────

class TestSaveConfidenceDecay:
    def _write_brain(self, path, patterns=None):
        brain = _make_brain(patterns or [_make_pattern("B-001", "web")])
        path.write_text(json.dumps(brain))

    def _write_interactions(self, path, entries):
        with path.open("w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def test_writes_updated_brain_to_file(self, tmp_path):
        brain_path = tmp_path / "ta_brain.json"
        interactions_path = tmp_path / "interactions.jsonl"
        self._write_brain(brain_path)
        self._write_interactions(interactions_path, [
            {"ts": "t0", "type": "feedback", "feedback": "wrong",
             "topology_signature": "sig_a", "arch_type": "web",
             "query_mode": "infer", "reference_ts": ""},
            {"ts": "t1", "type": "feedback", "feedback": "wrong",
             "topology_signature": "sig_a", "arch_type": "web",
             "query_mode": "infer", "reference_ts": ""},
            {"ts": "t2", "type": "feedback", "feedback": "wrong",
             "topology_signature": "sig_a", "arch_type": "web",
             "query_mode": "infer", "reference_ts": ""},
        ])

        with patch("chatbot.modules.ta_brain_confidence.BRAIN_PATH", brain_path):
            result = save_confidence_decay(brain_path, interactions_path)

        brain = json.loads(brain_path.read_text())
        p = brain["patterns"][0]
        assert p["corpus_confidence"] < 1.0  # decayed
        assert result["total_wrong"] == 3

    def test_returns_confidence_deltas(self, tmp_path):
        brain_path = tmp_path / "ta_brain.json"
        interactions_path = tmp_path / "interactions.jsonl"
        self._write_brain(brain_path, [_make_pattern("B-001", "web", corpus_conf=0.8)])
        self._write_interactions(interactions_path, [
            {"ts": "t0", "type": "feedback", "feedback": "wrong",
             "topology_signature": "sig_a", "arch_type": "web",
             "query_mode": "infer", "reference_ts": ""},
        ])
        result = save_confidence_decay(brain_path, interactions_path)
        assert "B-001" in result["confidence_deltas"]
        assert result["confidence_deltas"]["B-001"] < 0  # negative delta

    def test_suspect_patterns_in_summary(self, tmp_path):
        brain_path = tmp_path / "ta_brain.json"
        interactions_path = tmp_path / "interactions.jsonl"
        self._write_brain(brain_path)
        # Write SUSPECT_MIN_WRONG wrong feedbacks
        entries = [
            {"ts": f"t{i}", "type": "feedback", "feedback": "wrong",
             "topology_signature": "sig_a", "arch_type": "web",
             "query_mode": "infer", "reference_ts": ""}
            for i in range(SUSPECT_MIN_WRONG)
        ]
        self._write_interactions(interactions_path, entries)
        result = save_confidence_decay(brain_path, interactions_path)
        assert "B-001" in result["suspect_patterns"]

    def test_raises_when_brain_not_found(self, tmp_path):
        with pytest.raises(ValueError, match="Brain not found"):
            save_confidence_decay(tmp_path / "nonexistent.json")

    def test_no_change_when_no_feedback(self, tmp_path):
        brain_path = tmp_path / "ta_brain.json"
        interactions_path = tmp_path / "interactions.jsonl"
        self._write_brain(brain_path)
        interactions_path.write_text("")
        result = save_confidence_decay(brain_path, interactions_path)
        assert result["total_confirmed"] == 0
        assert result["total_wrong"] == 0
        assert result["confidence_deltas"] == {}


# ── Integration: suspect_patterns in query response ───────────────────────────

class TestSuspectInQueryResponse:
    """Verify _run_infer surfaces suspect patterns in response."""

    def test_suspect_pattern_surfaces_in_response(self):
        from chatbot.modules.ta_brain_query import _run_infer

        suspect_pattern = _make_pattern("B-001", "web", suspect=True)
        brain = _make_brain([suspect_pattern])
        result = _run_infer("any_sig", "web", brain)

        assert result["had_match"] is True
        assert "B-001" in result.get("suspect_patterns", [])

    def test_clean_pattern_has_empty_suspect_list(self):
        from chatbot.modules.ta_brain_query import _run_infer

        clean_pattern = _make_pattern("B-001", "web", suspect=False)
        brain = _make_brain([clean_pattern])
        result = _run_infer("any_sig", "web", brain)

        assert result.get("suspect_patterns", []) == []
