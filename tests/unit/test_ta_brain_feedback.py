"""
Unit tests — Stage 3: interaction log feedback write-back.

All tests are deterministic: no LLM calls, no network.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from chatbot.modules.ta_brain_feedback import (
    VALID_FEEDBACK,
    get_feedback_summary,
    record_feedback,
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


# ── record_feedback ───────────────────────────────────────────────────────────

class TestRecordFeedback:
    def test_appends_feedback_entry_to_log(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        with patch("chatbot.modules.ta_brain_feedback.INTERACTIONS_PATH", log):
            result = record_feedback("sig_abc", "web", "infer", "confirmed")

        assert result["recorded"] is True
        entries = [json.loads(l) for l in log.read_text().strip().splitlines()]
        assert len(entries) == 1
        e = entries[0]
        assert e["type"] == "feedback"
        assert e["feedback"] == "confirmed"
        assert e["topology_signature"] == "sig_abc"
        assert e["arch_type"] == "web"
        assert e["query_mode"] == "infer"

    def test_append_only_does_not_modify_prior_entries(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        # Pre-populate with a query entry
        log.write_text(json.dumps({"ts": "t0", "query_mode": "infer",
                                   "topology_signature": "sig_abc"}) + "\n")
        with patch("chatbot.modules.ta_brain_feedback.INTERACTIONS_PATH", log):
            record_feedback("sig_abc", "web", "infer", "confirmed")

        lines = log.read_text().strip().splitlines()
        assert len(lines) == 2
        first = json.loads(lines[0])
        assert first["ts"] == "t0"   # original entry unchanged

    def test_reference_ts_stored_in_entry(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        with patch("chatbot.modules.ta_brain_feedback.INTERACTIONS_PATH", log):
            record_feedback("sig_abc", "web", "infer", "wrong",
                            reference_ts="2026-08-12T10:00:00Z")

        entry = json.loads(log.read_text())
        assert entry["reference_ts"] == "2026-08-12T10:00:00Z"

    def test_invalid_feedback_returns_error(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        with patch("chatbot.modules.ta_brain_feedback.INTERACTIONS_PATH", log):
            result = record_feedback("sig_abc", "web", "infer", "unsure")
        assert "error" in result
        assert not log.exists()  # nothing written

    def test_missing_topology_sig_returns_error(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        with patch("chatbot.modules.ta_brain_feedback.INTERACTIONS_PATH", log):
            result = record_feedback("", "web", "infer", "confirmed")
        assert "error" in result

    def test_confirmed_propagates_to_cache(self, tmp_path):
        from chatbot.modules.ta_brain_cache import CacheManager
        cache_path = tmp_path / "ta_brain_cache.json"
        cache = CacheManager(cache_path)
        # Pre-write a cache entry
        cache.write("sig_abc", "web", "infer", {}, {"had_match": True}, pattern_version=1)

        log = tmp_path / "interactions.jsonl"
        with patch("chatbot.modules.ta_brain_feedback.INTERACTIONS_PATH", log), \
             patch("chatbot.modules.ta_brain_cache.CACHE_PATH", cache_path):
            _reset_cache()
            result = record_feedback("sig_abc", "web", "infer", "confirmed")

        assert result["cache_updated"] is True
        cache2 = CacheManager(cache_path)
        s = cache2.stats()
        assert s["confirmed_entries"] == 1

    def test_wrong_evicts_cache_entry(self, tmp_path):
        from chatbot.modules.ta_brain_cache import CacheManager
        cache_path = tmp_path / "ta_brain_cache.json"
        cache = CacheManager(cache_path)
        cache.write("sig_abc", "web", "infer", {}, {"had_match": True}, pattern_version=1)

        log = tmp_path / "interactions.jsonl"
        with patch("chatbot.modules.ta_brain_feedback.INTERACTIONS_PATH", log), \
             patch("chatbot.modules.ta_brain_cache.CACHE_PATH", cache_path):
            _reset_cache()
            result = record_feedback("sig_abc", "web", "infer", "wrong")

        assert result["cache_updated"] is True
        cache2 = CacheManager(cache_path)
        s = cache2.stats()
        assert s["total"] == 0  # evicted

    def test_partial_feedback_logged_no_cache_change(self, tmp_path):
        from chatbot.modules.ta_brain_cache import CacheManager
        cache_path = tmp_path / "ta_brain_cache.json"
        cache = CacheManager(cache_path)
        cache.write("sig_abc", "web", "infer", {}, {"had_match": True}, pattern_version=1)

        log = tmp_path / "interactions.jsonl"
        with patch("chatbot.modules.ta_brain_feedback.INTERACTIONS_PATH", log), \
             patch("chatbot.modules.ta_brain_cache.CACHE_PATH", cache_path):
            _reset_cache()
            result = record_feedback("sig_abc", "web", "infer", "partial")

        # partial: logged but cache_updated=False (no entry for "partial" in record_feedback)
        assert result["recorded"] is True
        cache2 = CacheManager(cache_path)
        s = cache2.stats()
        assert s["total"] == 1  # still there

    def test_does_not_raise_on_log_write_failure(self, tmp_path):
        bad_path = tmp_path / "no_dir" / "interactions.jsonl"
        with patch("chatbot.modules.ta_brain_feedback.INTERACTIONS_PATH", bad_path):
            result = record_feedback("sig_abc", "web", "infer", "confirmed")
        # recorded=False but no exception raised
        assert result["recorded"] is False

    def test_all_valid_feedback_values_accepted(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        with patch("chatbot.modules.ta_brain_feedback.INTERACTIONS_PATH", log):
            for fb in VALID_FEEDBACK:
                result = record_feedback(f"sig_{fb}", "web", "infer", fb)
                assert "error" not in result, f"Unexpected error for feedback={fb}"


# ── get_feedback_summary ──────────────────────────────────────────────────────

class TestGetFeedbackSummary:
    def _write_log(self, path, entries):
        with path.open("w") as f:
            for e in entries:
                f.write(json.dumps(e) + "\n")

    def test_counts_queries_and_feedback_separately(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        self._write_log(log, [
            {"ts": "t0", "query_mode": "infer", "topology_signature": "s1",
             "arch_type": "web", "cache_route": "new"},
            {"ts": "t1", "query_mode": "infer", "topology_signature": "s1",
             "arch_type": "web", "cache_route": "new"},
            {"ts": "t2", "type": "feedback", "feedback": "confirmed",
             "topology_signature": "s1", "arch_type": "web",
             "query_mode": "infer", "reference_ts": "t0"},
        ])
        summary = get_feedback_summary(log)
        assert summary["total_queries"] == 2
        assert summary["total_feedback"] == 1

    def test_counts_by_pattern_sig(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        self._write_log(log, [
            {"ts": "t0", "type": "feedback", "feedback": "confirmed",
             "topology_signature": "sig_a", "arch_type": "web",
             "query_mode": "infer", "reference_ts": ""},
            {"ts": "t1", "type": "feedback", "feedback": "wrong",
             "topology_signature": "sig_a", "arch_type": "web",
             "query_mode": "infer", "reference_ts": ""},
            {"ts": "t2", "type": "feedback", "feedback": "confirmed",
             "topology_signature": "sig_a", "arch_type": "web",
             "query_mode": "infer", "reference_ts": ""},
        ])
        summary = get_feedback_summary(log)
        key = "sig_a:web:infer"
        assert summary["by_pattern_sig"][key]["confirmed"] == 2
        assert summary["by_pattern_sig"][key]["wrong"] == 1

    def test_empty_log_returns_zeros(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        log.write_text("")
        summary = get_feedback_summary(log)
        assert summary["total_queries"] == 0
        assert summary["total_feedback"] == 0

    def test_missing_log_returns_zeros(self, tmp_path):
        missing = tmp_path / "nonexistent.jsonl"
        summary = get_feedback_summary(missing)
        assert summary["total_queries"] == 0

    def test_multiple_modes_tracked_separately(self, tmp_path):
        log = tmp_path / "interactions.jsonl"
        self._write_log(log, [
            {"ts": "t0", "type": "feedback", "feedback": "confirmed",
             "topology_signature": "sig_a", "arch_type": "web",
             "query_mode": "infer", "reference_ts": ""},
            {"ts": "t1", "type": "feedback", "feedback": "wrong",
             "topology_signature": "sig_a", "arch_type": "web",
             "query_mode": "patterns", "reference_ts": ""},
        ])
        summary = get_feedback_summary(log)
        assert "sig_a:web:infer" in summary["by_pattern_sig"]
        assert "sig_a:web:patterns" in summary["by_pattern_sig"]
