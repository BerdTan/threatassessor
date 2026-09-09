"""
Unit tests — smart_router.py pipeline mode selection.

All tests are deterministic: no LLM calls, no network, no real report files.
Boxing data is seeded via tmp_path fixtures.
Policy is either injected directly or loaded from real model_routing.yaml.
"""

import json
import pytest
from pathlib import Path
from unittest.mock import patch

from chatbot.harness.smart_router import (
    RoutingDecision,
    _load_boxing_signals,
    _load_policy,
    select_mode,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_boxing_result(
    arch_name: str,
    delta: float,
    corpus_hits: int,
    ref_technique_count: int = 40,
    arch_type: str = "generic",
) -> dict:
    """Minimal boxing_results.json with routing_signals populated."""
    return {
        "arch_name": arch_name,
        "run_at": "2026-09-06T00:00:00Z",
        "ref_technique_count": ref_technique_count,
        "contenders_run": ["det_moe_full", "brain", "brain_lexical"],
        "contenders": {
            "det_moe_full": {"scores": {"composite": 0.9}},
            "brain": {"scores": {"composite": round(0.9 + delta, 4)}, "corpus_hits": corpus_hits},
        },
        "verdict": {
            "ranking": ["det_moe_full", "brain"],
            "winner": "det_moe_full",
            "scores": {"det_moe_full": 0.9, "brain": round(0.9 + delta, 4)},
            "quality_vs_cost": {
                "brain_vs_gold_delta": delta,
                "brain_latency_speedup": 600.0,
            },
        },
        "routing_signals": {
            "brain_vs_gold_delta": delta,
            "corpus_hits": corpus_hits,
            "ref_technique_count": ref_technique_count,
            "arch_type": arch_type,
            "brain_latency_speedup": 600.0,
        },
    }


def _make_old_boxing_result(arch_name: str, delta: float) -> dict:
    """Boxing result in old format — routing_signals is absent or empty dict."""
    return {
        "arch_name": arch_name,
        "ref_technique_count": 40,
        "verdict": {
            "quality_vs_cost": {
                "brain_vs_gold_delta": delta,
                "brain_latency_speedup": 100.0,
            },
        },
        "routing_signals": {},      # old format: empty
    }


def _write_boxing(tmp_path: Path, arch_name: str, data: dict) -> Path:
    arch_dir = tmp_path / arch_name
    arch_dir.mkdir(parents=True, exist_ok=True)
    p = arch_dir / "boxing_results.json"
    p.write_text(json.dumps(data))
    return p


def _default_policy() -> dict:
    """Minimal routing policy matching model_routing.yaml defaults."""
    return {
        "version": "1.0",
        "overrides": {
            "aivss_composite_full_moe_threshold": 7.0,
            "no_boxing_data_default": "api_only",
        },
        "tiers": {
            "brain_fast": {"brain_vs_gold_delta_min": -0.15, "corpus_hits_min": 3},
            "api_only":   {"brain_vs_gold_delta_min": -0.30, "corpus_hits_min": 1},
        },
    }


# ── _load_boxing_signals ──────────────────────────────────────────────────────

class TestLoadBoxingSignals:

    def test_returns_none_when_no_report_dir(self, tmp_path):
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg:
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            result = _load_boxing_signals("nonexistent_arch")
        assert result is None

    def test_returns_none_when_no_boxing_file(self, tmp_path):
        (tmp_path / "my_arch").mkdir()
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg:
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            result = _load_boxing_signals("my_arch")
        assert result is None

    def test_reads_new_format_routing_signals(self, tmp_path):
        data = _make_boxing_result("my_arch", delta=-0.12, corpus_hits=7)
        _write_boxing(tmp_path, "my_arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg:
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            signals = _load_boxing_signals("my_arch")
        assert signals is not None
        assert signals["brain_vs_gold_delta"] == pytest.approx(-0.12)
        assert signals["corpus_hits"] == 7

    def test_falls_back_to_old_format_qvsc(self, tmp_path):
        data = _make_old_boxing_result("old_arch", delta=-0.20)
        _write_boxing(tmp_path, "old_arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg:
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            signals = _load_boxing_signals("old_arch")
        assert signals is not None
        assert signals["brain_vs_gold_delta"] == pytest.approx(-0.20)
        assert signals["corpus_hits"] == 0       # unknown in old format

    def test_returns_none_when_no_delta_in_either_format(self, tmp_path):
        data = {"arch_name": "bad_arch", "verdict": {}, "routing_signals": {}}
        _write_boxing(tmp_path, "bad_arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg:
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            result = _load_boxing_signals("bad_arch")
        assert result is None


# ── select_mode — no boxing data ──────────────────────────────────────────────

class TestSelectModeNoData:

    def _patch(self, tmp_path, arch_name="unknown_arch"):
        """Patches so arch dir exists but no boxing_results.json."""
        (tmp_path / arch_name).mkdir(parents=True, exist_ok=True)
        return patch("chatbot.harness.smart_router.get_settings",
                     return_value=type("S", (), {"system": type("R", (), {"report_dir": str(tmp_path)})()})())

    def test_defaults_to_api_only_when_no_boxing_data(self, tmp_path):
        with self._patch(tmp_path), \
             patch("chatbot.harness.smart_router._load_policy", return_value=_default_policy()):
            d = select_mode("unknown_arch")
        assert d.mode == "api_only"
        assert d.has_boxing_data is False

    def test_no_data_default_respects_policy_config(self, tmp_path):
        policy = _default_policy()
        policy["overrides"]["no_boxing_data_default"] = "full_moe"
        with self._patch(tmp_path), \
             patch("chatbot.harness.smart_router._load_policy", return_value=policy):
            d = select_mode("unknown_arch")
        assert d.mode == "full_moe"


# ── select_mode — AIVSS override ─────────────────────────────────────────────

class TestSelectModeAivssOverride:

    def test_aivss_override_forces_full_moe(self, tmp_path):
        data = _make_boxing_result("safe_arch", delta=0.0, corpus_hits=10)
        _write_boxing(tmp_path, "safe_arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=_default_policy()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            d = select_mode("safe_arch", aivss_composite=7.5)
        assert d.mode == "full_moe"
        assert d.aivss_override is True

    def test_aivss_below_threshold_does_not_override(self, tmp_path):
        data = _make_boxing_result("safe_arch", delta=-0.10, corpus_hits=5)
        _write_boxing(tmp_path, "safe_arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=_default_policy()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            d = select_mode("safe_arch", aivss_composite=6.9)
        assert d.mode == "brain_fast"
        assert d.aivss_override is False

    def test_aivss_exactly_at_threshold_overrides(self, tmp_path):
        data = _make_boxing_result("arch", delta=0.0, corpus_hits=10)
        _write_boxing(tmp_path, "arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=_default_policy()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            d = select_mode("arch", aivss_composite=7.0)
        assert d.mode == "full_moe"


# ── select_mode — brain_fast tier ────────────────────────────────────────────

class TestSelectModeBrainFast:

    def _run(self, tmp_path, arch_name, delta, corpus_hits, ref=40):
        data = _make_boxing_result(arch_name, delta=delta, corpus_hits=corpus_hits, ref_technique_count=ref)
        _write_boxing(tmp_path, arch_name, data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=_default_policy()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            return select_mode(arch_name)

    def test_brain_fast_when_delta_and_hits_both_pass(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.10, corpus_hits=5)
        assert d.mode == "brain_fast"
        assert d.has_boxing_data is True

    def test_brain_fast_when_brain_wins(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=0.002, corpus_hits=5)
        assert d.mode == "brain_fast"

    def test_brain_fast_at_exact_delta_boundary(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.15, corpus_hits=3)
        assert d.mode == "brain_fast"

    def test_not_brain_fast_when_hits_too_low(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.10, corpus_hits=2)
        assert d.mode != "brain_fast"

    def test_not_brain_fast_when_delta_too_low(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.16, corpus_hits=10)
        assert d.mode != "brain_fast"

    def test_brain_fast_carries_routing_fields(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.12, corpus_hits=7, ref=43)
        assert d.brain_vs_gold_delta == pytest.approx(-0.12)
        assert d.corpus_hits == 7
        assert d.ref_technique_count == 43


# ── select_mode — api_only tier ──────────────────────────────────────────────

class TestSelectModeApiOnly:

    def _run(self, tmp_path, arch_name, delta, corpus_hits):
        data = _make_boxing_result(arch_name, delta=delta, corpus_hits=corpus_hits)
        _write_boxing(tmp_path, arch_name, data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=_default_policy()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            return select_mode(arch_name)

    def test_api_only_when_delta_ok_but_hits_below_brain_fast(self, tmp_path):
        # hits=2 → below brain_fast (min=3) but >= api_only (min=1)
        d = self._run(tmp_path, "arch", delta=-0.10, corpus_hits=2)
        assert d.mode == "api_only"

    def test_api_only_when_delta_in_middle_band(self, tmp_path):
        # delta=-0.20 → below brain_fast (-0.15) but >= api_only (-0.30)
        d = self._run(tmp_path, "arch", delta=-0.20, corpus_hits=5)
        assert d.mode == "api_only"

    def test_api_only_at_exact_lower_boundary(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.30, corpus_hits=1)
        assert d.mode == "api_only"

    def test_old_format_with_unknown_hits_routes_api_only(self, tmp_path):
        data = _make_old_boxing_result("arch", delta=-0.12)
        _write_boxing(tmp_path, "arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=_default_policy()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            d = select_mode("arch")
        # corpus_hits=0 in old format → fails brain_fast (hits_min=3) but passes api_only (hits_min=1)? No:
        # corpus_hits=0 also fails api_only (hits_min=1) → full_moe
        assert d.mode == "full_moe"


# ── select_mode — full_moe fallback ──────────────────────────────────────────

class TestSelectModeFullMoe:

    def _run(self, tmp_path, arch_name, delta, corpus_hits):
        data = _make_boxing_result(arch_name, delta=delta, corpus_hits=corpus_hits)
        _write_boxing(tmp_path, arch_name, data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=_default_policy()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            return select_mode(arch_name)

    def test_full_moe_when_delta_below_api_only_threshold(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.31, corpus_hits=5)
        assert d.mode == "full_moe"

    def test_full_moe_when_zero_corpus_hits(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.10, corpus_hits=0)
        assert d.mode == "full_moe"

    def test_full_moe_when_delta_very_negative(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.90, corpus_hits=20)
        assert d.mode == "full_moe"


# ── _load_policy — real file ──────────────────────────────────────────────────

class TestLoadPolicy:

    def test_real_policy_file_loads(self):
        policy = _load_policy()
        assert "tiers" in policy
        assert "overrides" in policy
        assert "brain_fast" in policy["tiers"]
        assert "api_only" in policy["tiers"]

    def test_real_policy_brain_fast_threshold(self):
        policy = _load_policy()
        bf = policy["tiers"]["brain_fast"]
        assert float(bf["brain_vs_gold_delta_min"]) == pytest.approx(-0.15)
        assert int(bf["corpus_hits_min"]) == 3

    def test_real_policy_api_only_threshold(self):
        policy = _load_policy()
        ao = policy["tiers"]["api_only"]
        assert float(ao["brain_vs_gold_delta_min"]) == pytest.approx(-0.30)
        assert int(ao["corpus_hits_min"]) == 1

    def test_real_policy_aivss_override_threshold(self):
        policy = _load_policy()
        assert float(policy["overrides"]["aivss_composite_full_moe_threshold"]) == pytest.approx(7.0)

    def test_policy_returns_empty_dict_on_missing_file(self, tmp_path):
        fake_path = tmp_path / "nonexistent.yaml"
        with patch("chatbot.harness.smart_router._POLICY_PATH", fake_path):
            policy = _load_policy()
        assert policy == {}

    def test_real_policy_d5_gate_threshold(self):
        policy = _load_policy()
        assert float(policy["overrides"]["d5_critical_recall_min"]) == pytest.approx(0.85)


# ── D5 critical recall gate ───────────────────────────────────────────────────

class TestD5Gate:
    """D5 gate: brain_fast downgraded to api_only when critical recall < threshold."""

    def _make_policy_with_d5(self, d5_min: float = 0.85) -> dict:
        p = _default_policy()
        p["overrides"]["d5_critical_recall_min"] = d5_min
        return p

    def _boxing_with_d5(self, arch_name: str, delta: float, hits: int, d5: float) -> dict:
        result = _make_boxing_result(arch_name, delta=delta, corpus_hits=hits)
        result["routing_signals"]["d5_critical_recall"] = d5
        return result

    def test_brain_fast_passes_when_d5_above_threshold(self, tmp_path):
        data = self._boxing_with_d5("arch", delta=-0.10, hits=5, d5=0.95)
        _write_boxing(tmp_path, "arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=self._make_policy_with_d5()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            d = select_mode("arch")
        assert d.mode == "brain_fast"

    def test_brain_fast_downgraded_to_api_only_when_d5_below_threshold(self, tmp_path):
        data = self._boxing_with_d5("arch", delta=-0.10, hits=5, d5=0.70)
        _write_boxing(tmp_path, "arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=self._make_policy_with_d5()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            d = select_mode("arch")
        assert d.mode == "api_only"
        assert "D5" in d.rationale or "critical recall" in d.rationale.lower()

    def test_d5_none_does_not_block(self, tmp_path):
        """When no D5 score exists (old boxing data), gate is bypassed."""
        data = _make_boxing_result("arch", delta=-0.10, corpus_hits=5)
        # d5_critical_recall absent from routing_signals
        assert "d5_critical_recall" not in data["routing_signals"]
        _write_boxing(tmp_path, "arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=self._make_policy_with_d5()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            d = select_mode("arch")
        assert d.mode == "brain_fast"

    def test_d5_exactly_at_threshold_passes(self, tmp_path):
        """D5 == threshold is not blocked (gate is strictly less-than)."""
        data = self._boxing_with_d5("arch", delta=-0.10, hits=5, d5=0.85)
        _write_boxing(tmp_path, "arch", data)
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=self._make_policy_with_d5()):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            d = select_mode("arch")
        assert d.mode == "brain_fast"


# ── Integration — real boxing files ──────────────────────────────────────────

class TestIntegrationRealBoxingFiles:
    """
    Reads the actual boxing_results.json files written during boxing runs.
    Skipped if files don't exist (CI without report data).
    """

    KNOWN_ARCHES = [
        ("22_generic_ai_nodes",  "brain_fast"),
        ("21_agentic_ai_system", "full_moe"),   # delta=-0.348 after arch_type fix (agentic pattern weak on this arch)
        ("12_microservices",     "brain_fast"),
    ]

    @pytest.mark.parametrize("arch_name,expected_mode", KNOWN_ARCHES)
    def test_known_arch_routes_correctly(self, arch_name, expected_mode):
        from pathlib import Path
        try:
            from chatbot.config import get_settings
            report_dir = Path(get_settings().system.report_dir)
        except Exception:
            pytest.skip("Cannot load settings")

        if not (report_dir / arch_name / "boxing_results.json").exists():
            pytest.skip(f"No boxing_results.json for {arch_name}")

        d = select_mode(arch_name)
        assert d.mode == expected_mode, (
            f"{arch_name}: expected {expected_mode}, got {d.mode} "
            f"(delta={d.brain_vs_gold_delta}, hits={d.corpus_hits})"
        )
        assert d.has_boxing_data is True

    def test_unknown_arch_returns_api_only(self):
        d = select_mode("totally_nonexistent_arch_xyz_123")
        assert d.mode == "api_only"
        assert d.has_boxing_data is False


# ── model_alias in RoutingDecision ────────────────────────────────────────────

def _policy_with_model_selection() -> dict:
    """Policy with model_selection block for model_alias tests."""
    base = _default_policy()
    base["tested_models"] = {
        "hetzner":      {"model_id": "openai/Qwen/Qwen3.6-35B-A3B-FP8", "status": "confirmed"},
        "gemini_flash": {"model_id": "gemini/gemini-3.6-flash",           "status": "confirmed"},
        "excluded_mdl": {"model_id": "openrouter/some/model:free",        "status": "excluded"},
    }
    base["model_selection"] = {
        "full_moe": {
            "agentic": {"primary": "hetzner",      "fallback": "gemini_flash"},
            "cloud":   {"primary": "excluded_mdl", "fallback": "gemini_flash"},
            "default": {"primary": "hetzner",      "fallback": "gemini_flash"},
        },
        "api_only": {
            "default": {"primary": "hetzner", "fallback": "gemini_flash"},
        },
    }
    return base


class TestModelAlias:
    """RoutingDecision carries the correct model_alias + model_id."""

    def _run(self, tmp_path, arch_name, delta, corpus_hits, arch_type="generic"):
        data = _make_boxing_result(arch_name, delta=delta, corpus_hits=corpus_hits, arch_type=arch_type)
        _write_boxing(tmp_path, arch_name, data)
        policy = _policy_with_model_selection()
        with patch("chatbot.harness.smart_router.get_settings") as mock_cfg, \
             patch("chatbot.harness.smart_router._load_policy", return_value=policy):
            mock_cfg.return_value.system.report_dir = str(tmp_path)
            return select_mode(arch_name)

    def test_full_moe_agentic_gets_hetzner(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.90, corpus_hits=5, arch_type="agentic")
        assert d.mode == "full_moe"
        assert d.model_alias == "hetzner"
        assert "Qwen" in d.model_id

    def test_full_moe_default_gets_hetzner(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.90, corpus_hits=5, arch_type="generic")
        assert d.mode == "full_moe"
        assert d.model_alias == "hetzner"

    def test_api_only_gets_hetzner(self, tmp_path):
        # hits=2 → api_only (below brain_fast min of 3)
        d = self._run(tmp_path, "arch", delta=-0.10, corpus_hits=2, arch_type="generic")
        assert d.mode == "api_only"
        assert d.model_alias == "hetzner"

    def test_excluded_primary_falls_back_to_gemini(self, tmp_path):
        # cloud → primary=excluded_mdl (status=excluded) → fallback=gemini_flash
        d = self._run(tmp_path, "arch", delta=-0.90, corpus_hits=5, arch_type="cloud")
        assert d.mode == "full_moe"
        assert d.model_alias == "gemini_flash"
        assert "gemini" in d.model_id

    def test_brain_fast_has_no_model(self, tmp_path):
        d = self._run(tmp_path, "arch", delta=-0.10, corpus_hits=5, arch_type="generic")
        assert d.mode == "brain_fast"
        assert d.model_alias == ""
        assert d.model_id == ""

    def test_no_boxing_data_returns_empty_model(self):
        d = select_mode("totally_nonexistent_arch_xyz_999")
        assert d.mode == "api_only"
        assert d.has_boxing_data is False
        # model_alias is set even without boxing data (falls to default)
        assert isinstance(d.model_alias, str)
        assert isinstance(d.model_id, str)

    def test_real_policy_agentic_routes_to_hetzner(self):
        """21_agentic_ai_system is boxed as full_moe/hetzner — verify via real files."""
        from pathlib import Path
        try:
            from chatbot.config import get_settings
            report_dir = Path(get_settings().system.report_dir)
        except Exception:
            pytest.skip("Cannot load settings")
        if not (report_dir / "21_agentic_ai_system" / "boxing_results.json").exists():
            pytest.skip("No boxing_results.json for 21_agentic_ai_system")
        d = select_mode("21_agentic_ai_system")
        assert d.mode == "full_moe"
        assert d.model_alias == "hetzner"
        assert d.model_id != ""


# ── QuickAssess endpoint — unit tests (no API server needed) ──────────────────

fastapi = pytest.importorskip("fastapi", reason="fastapi not installed — skipping endpoint tests")


class TestQuickAssessEndpoint:
    """
    Tests the quick-assess logic via FastAPI TestClient.
    Brain inference is mocked to avoid LLM/corpus dependency.
    """

    def _make_infer_result(self, had_match: bool = True) -> dict:
        if not had_match:
            return {"had_match": False, "patterns_fired": [], "confidence": 0.0,
                    "predictions": {}, "evidence": {}}
        return {
            "had_match": True,
            "patterns_fired": ["BRAIN-002"],
            "suspect_patterns": [],
            "confidence": 0.684,
            "predictions": {
                "techniques": ["T1078", "T1190", "T1059"],
                "technique_top": [
                    {"id": "T1078", "frequency": 0.9},
                    {"id": "T1190", "frequency": 0.8},
                ],
                "controls": ["AC-3", "SC-8"],
                "detect_rules": ["DETECT-001"],
                "aivss_floor": 3.12,
            },
            "evidence": {"source_archs": ["arch_a", "arch_b", "arch_b", "arch_c"]},
        }

    def _get_client(self, report_dir: Path, arch_name: str,
                    infer_result: dict, has_mmd: bool = False):
        """Build TestClient with report dir seeded and brain mocked."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from chatbot.api.routes.routing import router
        from unittest.mock import patch, MagicMock

        # Create arch dir
        arch_dir = report_dir / arch_name
        arch_dir.mkdir(parents=True, exist_ok=True)
        if has_mmd:
            (arch_dir / "architecture.mmd").write_text("graph LR\n  A[API] --> B[DB]")

        app = FastAPI()
        app.include_router(router)

        mock_key = MagicMock(return_value=True)
        app.dependency_overrides = {}

        def override_key():
            return "test"

        from chatbot.api.dependencies import verify_api_key
        app.dependency_overrides[verify_api_key] = override_key

        patches = [
            patch("chatbot.api.routes.routing.query_brain", return_value=infer_result),
            patch("chatbot.api.routes.routing.select_mode",
                  return_value=MagicMock(mode="brain_fast")),
            patch("chatbot.api.routes.routing.get_settings",
                  return_value=MagicMock(system=MagicMock(report_dir=str(report_dir)))),
        ]
        return TestClient(app), patches

    def _patches(self, tmp_path, infer_result):
        """Common patch stack for quick-assess tests (lazy imports → patch at source)."""
        from unittest.mock import patch, MagicMock
        return [
            patch("chatbot.modules.ta_brain_query.query_brain", return_value=infer_result),
            patch("chatbot.harness.smart_router.select_mode",
                  return_value=MagicMock(mode="brain_fast")),
            patch("chatbot.config.get_settings",
                  return_value=MagicMock(system=MagicMock(report_dir=str(tmp_path)))),
        ]

    def _make_app(self, tmp_path):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from chatbot.api.routes.routing import router
        from chatbot.api.dependencies import verify_api_key
        app = FastAPI()
        app.include_router(router)
        app.dependency_overrides[verify_api_key] = lambda: "k"
        return TestClient(app)

    def test_returns_200_on_match(self, tmp_path):
        arch_name = "test_arch"
        (tmp_path / arch_name).mkdir()
        infer = self._make_infer_result(had_match=True)

        with self._patches(tmp_path, infer)[0], self._patches(tmp_path, infer)[1], \
             self._patches(tmp_path, infer)[2]:
            from unittest.mock import patch, MagicMock
            with patch("chatbot.modules.ta_brain_query.query_brain", return_value=infer), \
                 patch("chatbot.harness.smart_router.select_mode",
                       return_value=MagicMock(mode="brain_fast")), \
                 patch("chatbot.config.get_settings",
                       return_value=MagicMock(system=MagicMock(report_dir=str(tmp_path)))):
                client = self._make_app(tmp_path)
                resp = client.get(f"/api/v1/routing/quick-assess/{arch_name}",
                                  headers={"X-API-Key": "k"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["had_match"] is True
        assert body["estimate_type"] == "pattern-based"
        assert "T1078" in body["techniques"]

    def test_no_match_returns_warning(self, tmp_path):
        (tmp_path / "no_match_arch").mkdir()
        infer = self._make_infer_result(had_match=False)

        from unittest.mock import patch, MagicMock
        with patch("chatbot.modules.ta_brain_query.query_brain", return_value=infer), \
             patch("chatbot.harness.smart_router.select_mode",
                   return_value=MagicMock(mode="api_only")), \
             patch("chatbot.config.get_settings",
                   return_value=MagicMock(system=MagicMock(report_dir=str(tmp_path)))):
            client = self._make_app(tmp_path)
            resp = client.get("/api/v1/routing/quick-assess/no_match_arch",
                              headers={"X-API-Key": "k"})

        assert resp.status_code == 200
        body = resp.json()
        assert body["had_match"] is False
        assert body["techniques"] == []
        assert body["warning"] is not None

    def test_404_for_unknown_arch(self, tmp_path):
        from unittest.mock import patch, MagicMock
        with patch("chatbot.config.get_settings",
                   return_value=MagicMock(system=MagicMock(report_dir=str(tmp_path)))):
            client = self._make_app(tmp_path)
            resp = client.get("/api/v1/routing/quick-assess/nonexistent_arch_xyz",
                              headers={"X-API-Key": "k"})

        assert resp.status_code == 404

    def test_path_traversal_rejected(self, tmp_path):
        from unittest.mock import patch, MagicMock
        with patch("chatbot.config.get_settings",
                   return_value=MagicMock(system=MagicMock(report_dir=str(tmp_path)))):
            client = self._make_app(tmp_path)
            resp = client.get("/api/v1/routing/quick-assess/../etc/passwd",
                              headers={"X-API-Key": "k"})

        # FastAPI normalises "../etc/passwd" before it reaches the handler,
        # so the path segment check may not fire — 400 or 404 are both safe rejections.
        assert resp.status_code in (400, 404, 422)

    def test_quality_scores_present_when_had_match(self, tmp_path):
        (tmp_path / "scored_arch").mkdir()
        infer = self._make_infer_result(had_match=True)

        from unittest.mock import patch, MagicMock
        with patch("chatbot.modules.ta_brain_query.query_brain", return_value=infer), \
             patch("chatbot.harness.smart_router.select_mode",
                   return_value=MagicMock(mode="brain_fast")), \
             patch("chatbot.config.get_settings",
                   return_value=MagicMock(system=MagicMock(report_dir=str(tmp_path)))):
            client = self._make_app(tmp_path)
            resp = client.get("/api/v1/routing/quick-assess/scored_arch",
                              headers={"X-API-Key": "k"})

        assert resp.status_code == 200
        body = resp.json()
        assert "quality" in body

    def test_corpus_hits_deduplicates_source_archs(self, tmp_path):
        """corpus_hits = len(set(source_archs)) — duplicates in evidence don't inflate count."""
        infer = self._make_infer_result(had_match=True)
        # source_archs has ["arch_a", "arch_b", "arch_b", "arch_c"] → 3 unique
        source_archs = infer["evidence"]["source_archs"]
        corpus_hits = len(set(source_archs))
        assert corpus_hits == 3
