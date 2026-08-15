"""Unit tests for TACOBenchmark 7-dimension scorer (18 tests)."""

from __future__ import annotations

import json
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from chatbot.modules.taco_benchmark import (
    BenchmarkResult,
    BenchmarkScore,
    TACOBenchmark,
    _compute_overall,
    _dim_confidence_calibration,
    _dim_ciso_utility,
    _dim_groundedness,
    _dim_risk_defensible,
    _dim_threat_relevant,
    _dim_ttp_accurate,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gt(
    techs=("T1078", "T1190"),
    confirmed=("T1078",),
    missing=("mfa", "waf"),
) -> dict:
    return {
        "techniques": list(techs),
        "controls_missing": list(missing),
        "technique_validation": [{"technique": t, "valid": True} for t in confirmed],
    }


def _make_arch(tmp_path: Path, arch_name: str, gt: dict) -> Path:
    d = tmp_path / arch_name
    d.mkdir()
    (d / "ground_truth.json").write_text(json.dumps(gt))
    return d


def _blank_score(**kwargs) -> BenchmarkScore:
    defaults = dict(
        arch_name="test", mode="workspace",
        threat_relevant=50.0, ttp_accurate=50.0, risk_defensible=50.0,
        plan_actionable=None, groundedness=50.0,
        confidence_calibration=50.0, ciso_utility=50.0, overall=0.0,
        duration_ms=0,
    )
    defaults.update(kwargs)
    return BenchmarkScore(**defaults)


# ---------------------------------------------------------------------------
# BenchmarkScore structure
# ---------------------------------------------------------------------------

def test_benchmark_score_fields_all_present():
    s = _blank_score()
    d = s.to_dict()
    for dim in ("threat_relevant", "ttp_accurate", "risk_defensible", "plan_actionable",
                "groundedness", "confidence_calibration", "ciso_utility", "overall"):
        assert dim in d["scores"], f"missing dim: {dim}"


def test_benchmark_result_has_three_series():
    s = _blank_score()
    r = BenchmarkResult(
        arch_name="test", workspace=s, taco_brain=s, taco_rag=s, scored_at="2026-08-15T00:00:00Z"
    )
    d = r.to_dict()
    assert set(d["series"].keys()) == {"workspace", "taco_brain", "taco_rag"}


# ---------------------------------------------------------------------------
# Dimension: Threat-Relevant
# ---------------------------------------------------------------------------

def test_dim_threat_relevant_empty_actual_returns_50():
    assert _dim_threat_relevant(set(), {}) == 50.0


def test_dim_threat_relevant_full_coverage_returns_100():
    gt = _make_gt(techs=("T1078", "T1190"))
    assert _dim_threat_relevant({"T1078", "T1190", "T1234"}, gt) == 100.0


def test_dim_threat_relevant_partial_coverage():
    gt = _make_gt(techs=("T1078", "T1190", "T1234", "T1235", "T1236", "T1237"))
    assert _dim_threat_relevant({"T1078", "T1190", "T1234"}, gt) == 50.0


# ---------------------------------------------------------------------------
# Dimension: TTP-Accurate
# ---------------------------------------------------------------------------

def test_dim_ttp_accurate_no_validation_returns_50():
    gt = {"techniques": ["T1078"], "technique_validation": []}
    assert _dim_ttp_accurate({"T1078"}, gt) == 50.0


def test_dim_ttp_accurate_all_confirmed():
    gt = _make_gt(techs=("T1078", "T1190"), confirmed=("T1078", "T1190"))
    assert _dim_ttp_accurate({"T1078", "T1190"}, gt) == 100.0


# ---------------------------------------------------------------------------
# Dimension: Risk-Defensible
# ---------------------------------------------------------------------------

def test_dim_risk_defensible_control_coverage():
    gt = _make_gt(missing=("mfa", "waf", "logging", "encryption"))
    assert _dim_risk_defensible({"mfa", "waf"}, gt) == 50.0


# ---------------------------------------------------------------------------
# Dimension: Groundedness
# ---------------------------------------------------------------------------

def test_dim_groundedness_weighted_formula():
    gt = _make_gt(techs=("T1078", "T1190"), missing=("mfa", "waf", "logging", "encryption", "patching"))
    predicted_techs = {"T1078"}      # 1/2 = 0.50
    predicted_controls = {"mfa"}    # 1/5 = 0.20
    # expected = round((0.50 * 0.60 + 0.20 * 0.40) * 100) = round(38.0) = 38
    result = _dim_groundedness(predicted_techs, predicted_controls, gt)
    assert result == 38.0


# ---------------------------------------------------------------------------
# Dimension: Confidence-Calibration
# ---------------------------------------------------------------------------

def test_dim_confidence_calibration_perfect_returns_100():
    assert _dim_confidence_calibration(1.0, 100.0) == 100.0


def test_dim_confidence_calibration_half_off_returns_0():
    # reported=1.0, actual_acc=0.5 → error=0.5 → score=0
    assert _dim_confidence_calibration(1.0, 50.0) == 0.0


# ---------------------------------------------------------------------------
# Dimension: CISO-Utility
# ---------------------------------------------------------------------------

def test_dim_ciso_utility_all_signals_returns_100():
    hop_summary = {
        "predicted_techs": ["T1078"],
        "predicted_controls": ["mfa"],
        "had_graph_hit": True,
        "final_confidence": 0.80,
        "brain_predictions": {"aivss_floor": 5.0},
    }
    assert _dim_ciso_utility(hop_summary, {}) == 100.0


def test_dim_ciso_utility_no_signals_returns_0():
    hop_summary = {
        "predicted_techs": [],
        "predicted_controls": [],
        "had_graph_hit": False,
        "final_confidence": 0.0,
        "brain_predictions": {"aivss_floor": 0.0},
    }
    assert _dim_ciso_utility(hop_summary, {}) == 0.0


# ---------------------------------------------------------------------------
# Overall computation
# ---------------------------------------------------------------------------

def test_compute_overall_skips_none_plan():
    s = _blank_score(
        threat_relevant=80.0, ttp_accurate=80.0, risk_defensible=80.0,
        plan_actionable=None, groundedness=80.0, confidence_calibration=80.0, ciso_utility=80.0,
    )
    overall = _compute_overall(s)
    # plan_actionable=None excluded; remaining weights: 0.20+0.20+0.15+0.15+0.10+0.10 = 0.90
    assert overall == round(80.0 * 0.90 / 0.90)


def test_compute_overall_all_none_returns_0():
    s = _blank_score(
        threat_relevant=None, ttp_accurate=None, risk_defensible=None,
        plan_actionable=None, groundedness=None, confidence_calibration=None, ciso_utility=None,
    )
    assert _compute_overall(s) == 0.0


# ---------------------------------------------------------------------------
# Integration: score_arch shape
# ---------------------------------------------------------------------------

def test_score_arch_returns_all_three_series(tmp_path):
    gt = _make_gt()
    _make_arch(tmp_path, "test_arch", gt)
    bm = TACOBenchmark(report_dir=tmp_path)

    mock_g = MagicMock()
    mock_g.query.return_value = None
    mock_g.attack_paths = {}
    mock_g.arch_controls_missing = {}

    mock_brain_hop = MagicMock()
    mock_brain_hop.hop_type = "brain"
    mock_brain_hop.confidence = 0.80
    mock_brain_hop.metadata = {"predictions": {"techniques": [], "missing_controls": [], "aivss_floor": 0.0}}

    mock_chain = MagicMock()
    mock_chain.chain_id = "abc"
    mock_chain.hops = [mock_brain_hop]

    with patch("chatbot.modules.graph_index.ThreatGraph") as MockTG, \
         patch("chatbot.modules.taco_agent.TACOAgent.run", return_value=mock_chain):
        MockTG.build.return_value = mock_g
        result = bm.score_arch("test_arch")

    assert isinstance(result, BenchmarkResult)
    assert result.workspace.mode == "workspace"
    assert result.taco_brain.mode == "taco_brain"
    assert result.taco_rag.mode == "taco_rag"
    for attr in ("threat_relevant", "ttp_accurate", "risk_defensible",
                 "groundedness", "confidence_calibration", "ciso_utility", "overall"):
        assert getattr(result.workspace, attr) is not None


def test_benchmark_is_deterministic(tmp_path):
    gt = _make_gt()
    _make_arch(tmp_path, "test_arch", gt)
    bm = TACOBenchmark(report_dir=tmp_path)

    mock_g = MagicMock()
    mock_g.query.return_value = "answer"
    mock_g.attack_paths = {"ap1": MagicMock(arch="test_arch", techniques=["T1078"])}
    mock_g.arch_controls_missing = {"test_arch": ["mfa"]}

    mock_brain_hop = MagicMock()
    mock_brain_hop.hop_type = "brain"
    mock_brain_hop.confidence = 0.80
    mock_brain_hop.metadata = {
        "predictions": {"techniques": ["T1078"], "missing_controls": ["mfa"], "aivss_floor": 5.0}
    }
    mock_chain = MagicMock()
    mock_chain.chain_id = "abc"
    mock_chain.hops = [mock_brain_hop]

    with patch("chatbot.modules.graph_index.ThreatGraph") as MockTG, \
         patch("chatbot.modules.taco_agent.TACOAgent.run", return_value=mock_chain):
        MockTG.build.return_value = mock_g
        r1 = bm.score_arch("test_arch")
        r2 = bm.score_arch("test_arch")

    assert r1.workspace.overall == r2.workspace.overall
    assert r1.taco_rag.overall == r2.taco_rag.overall


# ---------------------------------------------------------------------------
# HOLD_OUT_ARCHS sanity
# ---------------------------------------------------------------------------

def test_hold_out_archs_imported():
    from chatbot.modules.ta_brain_builder import HOLD_OUT_ARCHS
    assert len(HOLD_OUT_ARCHS) == 8
    assert all(isinstance(a, str) for a in HOLD_OUT_ARCHS)
