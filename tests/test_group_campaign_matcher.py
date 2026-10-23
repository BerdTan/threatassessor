"""
Unit tests for GroupCampaignMatcher.
No API, no LLM — uses the real enterprise-attack.json via the live pkl cache.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from chatbot.modules.group_campaign_matcher import (
    ActorMatch,
    GroupCampaignMatcher,
    _GroupEntry,
    get_matcher,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def matcher() -> GroupCampaignMatcher:
    return get_matcher()


# ---------------------------------------------------------------------------
# Index loading
# ---------------------------------------------------------------------------

class TestIndexLoad:
    def test_group_count(self, matcher):
        assert matcher.group_count == 187

    def test_known_group_exists(self, matcher):
        apt28 = matcher.get_group("G0007")
        assert apt28 is not None
        assert apt28.name == "APT28"

    def test_group_has_techniques(self, matcher):
        apt28 = matcher.get_group("G0007")
        assert len(apt28.techniques) > 10

    def test_group_has_tools(self, matcher):
        apt28 = matcher.get_group("G0007")
        assert len(apt28.tools) > 0

    def test_singleton_returns_same_object(self, matcher):
        m2 = get_matcher()
        assert matcher is m2


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

class TestMatch:
    def test_empty_techniques_returns_empty(self, matcher):
        assert matcher.match(set()) == []

    def test_returns_at_most_top_n(self, matcher):
        ttps = {"T1566", "T1078", "T1059", "T1027", "T1003", "T1021"}
        results = matcher.match(ttps, top_n=3)
        assert len(results) <= 3

    def test_sorted_descending_by_overlap(self, matcher):
        ttps = {"T1566", "T1078", "T1059", "T1027", "T1003", "T1021"}
        results = matcher.match(ttps, top_n=5)
        overlaps = [r.overlap_pct for r in results]
        assert overlaps == sorted(overlaps, reverse=True)

    def test_result_fields_populated(self, matcher):
        ttps = {"T1059", "T1078", "T1003"}
        results = matcher.match(ttps, top_n=1)
        assert results
        r = results[0]
        assert r.group_id.startswith("G")
        assert r.name
        assert 0.0 < r.overlap_pct <= 1.0
        assert r.matched_techniques
        assert all(t in ttps for t in r.matched_techniques)

    def test_min_overlap_filter(self, matcher):
        ttps = {"T1059", "T1078", "T1003", "T1021", "T1027", "T1566"}
        all_results = matcher.match(ttps, top_n=10, min_overlap=0.0)
        filtered = matcher.match(ttps, top_n=10, min_overlap=0.5)
        assert all(r.overlap_pct >= 0.5 for r in filtered)
        assert len(filtered) <= len(all_results)

    def test_to_dict_serialisable(self, matcher):
        ttps = {"T1059", "T1078"}
        results = matcher.match(ttps, top_n=1)
        if results:
            d = results[0].to_dict()
            assert set(d.keys()) == {
                "group_id", "name", "aliases", "overlap_pct",
                "matched_techniques", "tools"
            }

    def test_tools_capped_at_five(self, matcher):
        # All groups should return ≤ 5 tools
        ttps = {"T1059", "T1078", "T1003", "T1021", "T1027", "T1566",
                "T1190", "T1133", "T1098", "T1055"}
        results = matcher.match(ttps, top_n=10)
        for r in results:
            assert len(r.tools) <= 5

    def test_subtechnique_normalisation(self, matcher):
        # T1059.001 should match groups that use T1059
        ttps_sub = {"T1059.001", "T1078.002", "T1003.001"}
        results_sub = matcher.match(ttps_sub, top_n=3)
        # Should find some matches via base-technique normalisation
        assert len(results_sub) > 0

    def test_no_overlap_unknown_techniques(self, matcher):
        fake_ttps = {"T9999", "T8888", "T7777"}
        results = matcher.match(fake_ttps, top_n=3)
        assert results == []


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class TestCache:
    def test_pkl_written_after_build(self, matcher, tmp_path):
        """Building from a temp copy of the STIX file produces a pkl."""
        import json, shutil
        stix_src = Path("chatbot/data/enterprise-attack.json")
        if not stix_src.exists():
            pytest.skip("enterprise-attack.json not present")

        tmp_stix = tmp_path / "enterprise-attack.json"
        shutil.copy(stix_src, tmp_stix)

        m = GroupCampaignMatcher(tmp_stix)
        pkl = tmp_stix.with_suffix(".gcm.pkl")
        assert pkl.exists()
        assert m.group_count == 187

    def test_corrupted_pkl_falls_back_to_rebuild(self, tmp_path):
        """A corrupted pkl triggers a clean rebuild without raising."""
        import json, shutil
        stix_src = Path("chatbot/data/enterprise-attack.json")
        if not stix_src.exists():
            pytest.skip("enterprise-attack.json not present")

        tmp_stix = tmp_path / "enterprise-attack.json"
        shutil.copy(stix_src, tmp_stix)
        # Write garbage pkl with mtime older than stix so it skips cache
        pkl = tmp_stix.with_suffix(".gcm.pkl")
        pkl.write_bytes(b"not valid pickle data")
        import os, time
        os.utime(pkl, (time.time() - 10, time.time() - 10))

        m = GroupCampaignMatcher(tmp_stix)
        assert m.group_count == 187
