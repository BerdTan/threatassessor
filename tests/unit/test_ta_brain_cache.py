"""
Unit tests — Stage 2.5: TACO cache layer.

All tests are deterministic: no LLM calls, no network.
CacheManager uses tmp_path so no real cache files are touched.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from chatbot.modules.ta_brain_cache import (
    VARIANT_THRESHOLD,
    CacheManager,
    extract_shape_counts,
    multiset_jaccard,
    reset_singleton,
    get_cache_manager,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_cache(tmp_path) -> CacheManager:
    return CacheManager(tmp_path / "ta_brain_cache.json")


def _make_response(had_match=True, confidence=0.8, patterns_fired=None) -> dict:
    return {
        "had_match": had_match,
        "patterns_fired": patterns_fired or ["BRAIN-001"],
        "confidence": confidence,
        "predictions": {"techniques": ["T1078"], "missing_controls": ["mfa"]},
        "evidence": {"pattern_ids": ["BRAIN-001"], "source_archs": ["arch_a"]},
    }


# ── extract_shape_counts ──────────────────────────────────────────────────────

class TestExtractShapeCounts:
    def test_counts_shapes_correctly(self):
        nodes = {
            "A": {"shape": "rectangle"},
            "B": {"shape": "rectangle"},
            "C": {"shape": "cylinder"},
        }
        counts = extract_shape_counts(nodes)
        assert counts == {"rectangle": 2, "cylinder": 1}

    def test_empty_nodes_returns_empty(self):
        assert extract_shape_counts({}) == {}

    def test_missing_shape_defaults_to_unknown(self):
        nodes = {"A": {"label": "no_shape_key"}}
        counts = extract_shape_counts(nodes)
        assert counts == {"unknown": 1}


# ── multiset_jaccard ──────────────────────────────────────────────────────────

class TestMultisetJaccard:
    def test_identical_returns_one(self):
        a = {"rectangle": 3, "cylinder": 2}
        assert multiset_jaccard(a, a) == 1.0

    def test_disjoint_returns_zero(self):
        a = {"rectangle": 2}
        b = {"cylinder": 3}
        assert multiset_jaccard(a, b) == 0.0

    def test_partial_overlap(self):
        a = {"rectangle": 4, "cylinder": 2}
        b = {"rectangle": 2, "circle": 2}
        # intersection: min(4,2)+min(2,0)+min(0,2) = 2+0+0 = 2
        # union: max(4,2)+max(2,0)+max(0,2) = 4+2+2 = 8
        j = multiset_jaccard(a, b)
        assert abs(j - 2 / 8) < 0.001

    def test_both_empty_returns_one(self):
        assert multiset_jaccard({}, {}) == 1.0

    def test_one_empty_returns_zero(self):
        assert multiset_jaccard({"rectangle": 1}, {}) == 0.0
        assert multiset_jaccard({}, {"rectangle": 1}) == 0.0

    def test_large_size_difference_low_similarity(self):
        small = {"rectangle": 2}
        large = {"rectangle": 20}
        j = multiset_jaccard(small, large)
        assert j < 0.3  # 2/20 = 0.1

    def test_same_shapes_same_counts_above_threshold(self):
        a = {"rectangle": 5, "cylinder": 3, "circle": 2}
        b = {"rectangle": 5, "cylinder": 3, "circle": 2}
        assert multiset_jaccard(a, b) >= VARIANT_THRESHOLD


# ── CacheManager.route ────────────────────────────────────────────────────────

class TestCacheManagerRoute:
    def test_exact_hit_returns_cached_response(self, tmp_path):
        cache = _make_cache(tmp_path)
        response = _make_response()
        cache.write("sig_abc", "web", "infer", {"rectangle": 3}, response, pattern_version=1)

        route, cached, *_ = cache.route("sig_abc", "web", "infer",
                                         current_pattern_version=1,
                                         shape_counts={"rectangle": 3})
        assert route == "hit"
        assert cached["had_match"] is True

    def test_hit_increments_hit_count(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_abc", "web", "infer", {}, _make_response(), pattern_version=1)

        cache.route("sig_abc", "web", "infer", 1)
        cache.route("sig_abc", "web", "infer", 1)

        # Reload from file to confirm persistence — use stats() to trigger _load()
        cache2 = _make_cache(tmp_path)
        s = cache2.stats()
        assert s["total_hits"] >= 2

    def test_stale_version_is_a_miss(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_abc", "web", "infer", {}, _make_response(), pattern_version=1)

        route, *_ = cache.route("sig_abc", "web", "infer", current_pattern_version=2)
        assert route == "miss"

    def test_unknown_sig_is_a_miss(self, tmp_path):
        cache = _make_cache(tmp_path)
        route, *_ = cache.route("unknown_sig", "web", "infer", current_pattern_version=1)
        assert route == "miss"

    def test_miss_labels_variant_when_jaccard_above_threshold(self, tmp_path):
        cache = _make_cache(tmp_path)
        # Write an entry for web arch with shape_counts
        cache.write("sig_existing", "web", "infer",
                    {"rectangle": 5, "cylinder": 3}, _make_response(), pattern_version=1)

        # Query with similar shape_counts (same shapes, similar counts)
        route, _, label = cache.route("sig_new", "web", "infer",
                                       current_pattern_version=1,
                                       shape_counts={"rectangle": 5, "cylinder": 3})
        assert route == "miss"
        assert label == "variant"

    def test_miss_labels_new_when_jaccard_below_threshold(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_existing", "web", "infer",
                    {"rectangle": 5, "cylinder": 3}, _make_response(), pattern_version=1)

        # Query with very different shape_counts
        route, _, label = cache.route("sig_new", "web", "infer",
                                       current_pattern_version=1,
                                       shape_counts={"hexagon": 1})
        assert label == "new"

    def test_miss_labels_new_when_no_shape_counts(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_a", "web", "infer", {"rectangle": 3}, _make_response(), pattern_version=1)

        route, _, label = cache.route("sig_b", "web", "infer", 1, shape_counts=None)
        assert label == "new"

    def test_different_arch_type_not_considered_variant(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_iot", "iot", "infer",
                    {"rectangle": 5, "cylinder": 3}, _make_response(), pattern_version=1)

        # Same shapes but different arch_type → new, not variant
        route, _, label = cache.route("sig_web", "web", "infer",
                                       current_pattern_version=1,
                                       shape_counts={"rectangle": 5, "cylinder": 3})
        assert label == "new"

    def test_different_mode_not_a_hit(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_abc", "web", "infer", {}, _make_response(), pattern_version=1)

        route, *_ = cache.route("sig_abc", "web", "gaps", 1)
        assert route == "miss"


# ── CacheManager.write ────────────────────────────────────────────────────────

class TestCacheManagerWrite:
    def test_entry_persisted_to_file(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_x", "web", "infer", {"rectangle": 2}, _make_response(), 1)

        raw = json.loads((tmp_path / "ta_brain_cache.json").read_text())
        assert "sig_x:web:infer" in raw["entries"]

    def test_overwrite_preserves_hit_count(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_x", "web", "infer", {}, _make_response(), 1)
        cache.route("sig_x", "web", "infer", 1)  # bump hit_count to 1
        cache.write("sig_x", "web", "infer", {}, _make_response(confidence=0.9), 2)  # refresh

        raw = json.loads((tmp_path / "ta_brain_cache.json").read_text())
        entry = raw["entries"]["sig_x:web:infer"]
        assert entry["hit_count"] >= 1  # preserved
        assert entry["pattern_version"] == 2


# ── CacheManager.record_feedback ─────────────────────────────────────────────

class TestCacheManagerFeedback:
    def test_confirmed_updates_timestamp(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_abc", "web", "infer", {}, _make_response(), 1)
        result = cache.record_feedback("sig_abc", "web", "infer", "confirmed")
        assert result is True
        entry = cache._entries["sig_abc:web:infer"]
        assert entry["last_confirmed_ts"] is not None

    def test_wrong_evicts_entry(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_abc", "web", "infer", {}, _make_response(), 1)
        cache.record_feedback("sig_abc", "web", "infer", "wrong")
        assert "sig_abc:web:infer" not in cache._entries

    def test_evicted_entry_causes_miss_on_next_route(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_abc", "web", "infer", {}, _make_response(), 1)
        cache.record_feedback("sig_abc", "web", "infer", "wrong")
        route, *_ = cache.route("sig_abc", "web", "infer", 1)
        assert route == "miss"

    def test_returns_false_for_unknown_entry(self, tmp_path):
        cache = _make_cache(tmp_path)
        assert cache.record_feedback("nonexistent", "web", "infer", "confirmed") is False


# ── CacheManager.evict_stale ──────────────────────────────────────────────────

class TestCacheManagerEvictStale:
    def test_removes_old_version_entries(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_a", "web", "infer", {}, _make_response(), pattern_version=1)
        cache.write("sig_b", "web", "infer", {}, _make_response(), pattern_version=2)

        removed = cache.evict_stale(current_pattern_version=2)
        assert removed == 1
        assert "sig_a:web:infer" not in cache._entries
        assert "sig_b:web:infer" in cache._entries

    def test_no_removal_when_all_current(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_a", "web", "infer", {}, _make_response(), pattern_version=3)
        assert cache.evict_stale(3) == 0


# ── CacheManager.pre_warm ─────────────────────────────────────────────────────

class TestCacheManagerPreWarm:
    def _make_instances(self):
        return [
            {"arch_id": "arch_a", "arch_type": "web", "topology_signature": "sig_a",
             "node_count": 5, "edge_count": 3, "source": "real"},
            {"arch_id": "arch_b", "arch_type": "iot", "topology_signature": "sig_b",
             "node_count": 8, "edge_count": 6, "source": "real"},
        ]

    def _make_brain(self):
        return {
            "version": 1,
            "pattern_version": 1,
            "patterns": [
                {
                    "id": "BRAIN-001",
                    "trigger": {"arch_type": "web", "node_count_min": 3},
                    "predicts": {
                        "techniques": ["T1078"],
                        "technique_frequencies": {"T1078": 0.8},
                        "detect_rules": [],
                        "aivss_floor": 0.3,
                        "aivss_mean": 0.5,
                        "common_missing_controls": ["mfa"],
                        "control_frequencies": {"mfa": 0.8},
                    },
                    "corpus_confidence": 0.8,
                    "benchmark_confidence": 1.0,
                    "evidence_count": 2,
                    "real_evidence_count": 2,
                    "evidence_arch_ids": ["arch_c", "arch_d"],
                    "trend": "stable",
                    "remediation_template": {"priority_controls": ["mfa"], "mmd_patch_stub": ""},
                }
            ],
            "gaps": [],
        }

    def test_writes_entries_for_all_instances(self, tmp_path):
        cache = _make_cache(tmp_path)
        instances = self._make_instances()
        brain = self._make_brain()

        from chatbot.modules.ta_brain_query import _run_infer
        written = cache.pre_warm(instances, brain, _run_infer, report_dir=tmp_path)
        assert written == 2

    def test_pre_warm_skips_already_cached_at_current_version(self, tmp_path):
        cache = _make_cache(tmp_path)
        instances = self._make_instances()
        brain = self._make_brain()

        from chatbot.modules.ta_brain_query import _run_infer
        cache.pre_warm(instances, brain, _run_infer, report_dir=tmp_path)
        written2 = cache.pre_warm(instances, brain, _run_infer, report_dir=tmp_path)
        assert written2 == 0  # all already cached at version 1

    def test_pre_warm_refreshes_stale_entries(self, tmp_path):
        cache = _make_cache(tmp_path)
        instances = self._make_instances()
        brain_v1 = self._make_brain()
        brain_v2 = {**self._make_brain(), "pattern_version": 2}

        from chatbot.modules.ta_brain_query import _run_infer
        cache.pre_warm(instances, brain_v1, _run_infer, report_dir=tmp_path)
        written = cache.pre_warm(instances, brain_v2, _run_infer, report_dir=tmp_path)
        assert written == 2  # stale entries refreshed


# ── CacheManager.stats ────────────────────────────────────────────────────────

class TestCacheManagerStats:
    def test_stats_returns_correct_counts(self, tmp_path):
        cache = _make_cache(tmp_path)
        cache.write("sig_a", "web", "infer", {}, _make_response(), 1)
        cache.write("sig_b", "iot", "infer", {}, _make_response(), 1)
        s = cache.stats()
        assert s["total"] == 2
        assert s["arch_types"]["web"] == 1
        assert s["arch_types"]["iot"] == 1

    def test_stats_empty_cache(self, tmp_path):
        cache = _make_cache(tmp_path)
        s = cache.stats()
        assert s["total"] == 0


# ── Integration: query_brain routes through cache ─────────────────────────────

class TestQueryBrainCacheIntegration:
    """Verify that query_brain serves from cache on second call."""

    def _setup(self, tmp_path):
        from chatbot.modules.ta_brain_builder import build_brain
        # Minimal arch setup
        for arch_id in ["arch1", "arch2"]:
            arch_dir = tmp_path / arch_id
            arch_dir.mkdir()
            gt = {
                "architecture": arch_id,
                "metadata": {
                    "architecture_type": "web",
                    "node_count": 3,
                    "edge_count": 2,
                    "parsed_nodes": {"A": {"label": "A", "shape": "rectangle"},
                                     "B": {"label": "B", "shape": "cylinder"}},
                    "parsed_edges": [{"source": "A", "target": "B"}],
                    "run_ts": "2026-08-12T00:00:00Z",
                    "run_id": f"{arch_id}_run",
                },
                "techniques": ["T1078", "T1059"],
                "controls_missing": ["mfa", "logging"],
            }
            gs = {"aivss": {"overall": {"composite": 0.3, "severity": "LOW"}}}
            (arch_dir / "ground_truth.json").write_text(json.dumps(gt))
            (arch_dir / "governance_signals.json").write_text(json.dumps(gs))
        build_brain(report_dir=tmp_path, hold_out=frozenset())
        return tmp_path

    def test_second_infer_call_is_cache_hit(self, tmp_path):
        self._setup(tmp_path)
        reset_singleton()

        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   tmp_path / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   tmp_path / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH",
                   tmp_path / "ta_brain_interactions.jsonl"), \
             patch("chatbot.modules.ta_brain_query.REPORT_DIR", tmp_path), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1), \
             patch("chatbot.modules.ta_brain_cache.CACHE_PATH",
                   tmp_path / "ta_brain_cache.json"):
            reset_singleton()
            from chatbot.modules.ta_brain_query import query_brain

            r1 = query_brain(mode="infer", arch_name="arch1")
            r2 = query_brain(mode="infer", arch_name="arch1")

        assert r1.get("cache_route") in ("new", "variant")
        assert r2.get("cache_route") == "cache_hit"

    def test_interaction_log_records_cache_route(self, tmp_path):
        self._setup(tmp_path)
        reset_singleton()
        log_path = tmp_path / "ta_brain_interactions.jsonl"

        with patch("chatbot.modules.ta_brain_query.BRAIN_PATH",
                   tmp_path / "ta_brain.json"), \
             patch("chatbot.modules.ta_brain_query.INSTANCES_PATH",
                   tmp_path / "ta_brain_instances.jsonl"), \
             patch("chatbot.modules.ta_brain_query.INTERACTIONS_PATH", log_path), \
             patch("chatbot.modules.ta_brain_query.REPORT_DIR", tmp_path), \
             patch("chatbot.modules.ta_brain_query._brain_version", -1), \
             patch("chatbot.modules.ta_brain_cache.CACHE_PATH",
                   tmp_path / "ta_brain_cache.json"):
            reset_singleton()
            from chatbot.modules.ta_brain_query import query_brain
            query_brain(mode="infer", arch_name="arch1")
            query_brain(mode="infer", arch_name="arch1")

        entries = [json.loads(l) for l in log_path.read_text().strip().splitlines()]
        assert len(entries) == 2
        assert entries[0]["cache_route"] in ("new", "variant")
        assert entries[1]["cache_route"] == "cache_hit"
