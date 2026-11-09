"""
Tests for brain_fast → brain_route redesign.

Principle: brain informs routing, never replaces the pipeline.
brain_fast routing now runs api_only and attaches brain annotations.
"""
import pytest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# _get_brain_annotations
# ---------------------------------------------------------------------------

class TestGetBrainAnnotations:
    def _import(self):
        from chatbot.api.routes.streaming import _get_brain_annotations
        return _get_brain_annotations

    def test_returns_none_when_no_match(self):
        fn = self._import()
        infer = {"had_match": False}
        with patch("chatbot.modules.ta_brain_query.query_brain", return_value=infer):
            assert fn("some_arch") is None

    def test_returns_annotation_seed_on_match(self):
        fn = self._import()
        infer = {
            "had_match": True,
            "confidence": 0.87,
            "patterns_fired": ["pat_001"],
            "predictions": {"techniques": ["T1190", "T1078"], "missing_controls": []},
        }
        with patch("chatbot.modules.ta_brain_query.query_brain", return_value=infer):
            ann = fn("my_arch")
        assert ann is not None
        assert ann["routing"] == "brain_fast"
        assert ann["confidence"] == 0.87
        assert ann["patterns_fired"] == ["pat_001"]
        assert ann["expected"] == ["T1190", "T1078"]
        # confirmed/novel/diverged not yet present — added by _enrich_brain_annotations
        assert "confirmed" not in ann

    def test_returns_none_on_import_error(self):
        fn = self._import()
        with patch("chatbot.modules.ta_brain_query.query_brain", side_effect=RuntimeError("unavailable")):
            assert fn("some_arch") is None


# ---------------------------------------------------------------------------
# _enrich_brain_annotations
# ---------------------------------------------------------------------------

class TestEnrichBrainAnnotations:
    def _import(self):
        from chatbot.api.routes.streaming import _enrich_brain_annotations
        return _enrich_brain_annotations

    def _ground_truth(self, technique_ids):
        return {
            "attack_paths": [{"technique_id": tid} for tid in technique_ids]
        }

    def test_confirmed_is_intersection(self):
        fn = self._import()
        ann = {"routing": "brain_fast", "confidence": 0.9, "patterns_fired": [], "expected": ["T1190", "T1078"]}
        gt = self._ground_truth(["T1190", "T1059"])
        result = fn(ann, gt)
        assert result["confirmed"] == ["T1190"]

    def test_novel_is_pipeline_minus_expected(self):
        fn = self._import()
        ann = {"routing": "brain_fast", "confidence": 0.9, "patterns_fired": [], "expected": ["T1190"]}
        gt = self._ground_truth(["T1190", "T1059"])
        result = fn(ann, gt)
        assert result["novel"] == ["T1059"]

    def test_diverged_is_expected_minus_pipeline(self):
        fn = self._import()
        ann = {"routing": "brain_fast", "confidence": 0.9, "patterns_fired": [], "expected": ["T1190", "T1078"]}
        gt = self._ground_truth(["T1190"])
        result = fn(ann, gt)
        assert result["diverged"] == ["T1078"]

    def test_all_empty_on_no_attack_paths(self):
        fn = self._import()
        ann = {"routing": "brain_fast", "confidence": 0.9, "patterns_fired": [], "expected": ["T1190"]}
        result = fn(ann, {})
        assert result["confirmed"] == []
        assert result["novel"] == []
        assert result["diverged"] == ["T1190"]

    def test_original_fields_preserved(self):
        fn = self._import()
        ann = {"routing": "brain_fast", "confidence": 0.75, "patterns_fired": ["p1"], "expected": []}
        result = fn(ann, {})
        assert result["routing"] == "brain_fast"
        assert result["confidence"] == 0.75
        assert result["patterns_fired"] == ["p1"]

    def test_skips_attack_paths_without_technique_id(self):
        fn = self._import()
        ann = {"routing": "brain_fast", "confidence": 0.9, "patterns_fired": [], "expected": ["T1190"]}
        gt = {"attack_paths": [{"name": "no-technique-field"}, {"technique_id": "T1190"}]}
        result = fn(ann, gt)
        assert result["confirmed"] == ["T1190"]
        assert result["novel"] == []


# ---------------------------------------------------------------------------
# build_export — brain_annotations field
# ---------------------------------------------------------------------------

class TestBuildExportBrainAnnotations:
    def test_brain_annotations_absent_when_none(self, tmp_path):
        from chatbot.modules.ta_exporter import build_export
        (tmp_path / "ground_truth.json").write_text('{"threats":{},"attack_paths":[]}')
        (tmp_path / "governance_signals.json").write_text('{}')
        result = build_export("test_arch", tmp_path)
        assert "brain_annotations" not in result

    def test_brain_annotations_present_when_provided(self, tmp_path):
        from chatbot.modules.ta_exporter import build_export
        (tmp_path / "ground_truth.json").write_text('{"threats":{},"attack_paths":[]}')
        (tmp_path / "governance_signals.json").write_text('{}')
        ann = {
            "routing": "brain_fast",
            "confidence": 0.88,
            "patterns_fired": ["pat_xyz"],
            "expected": ["T1190"],
            "confirmed": ["T1190"],
            "novel": [],
            "diverged": [],
        }
        result = build_export("test_arch", tmp_path, brain_annotations=ann)
        assert result["brain_annotations"] == ann
