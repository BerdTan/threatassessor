"""Unit tests for TACOminiRAG and Phase 3 TACOAgent routing (15 tests)."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest

from chatbot.modules.taco_agent import (
    HopChain,
    HopRecord,
    TACOAgent,
    TACOContext,
    TACOminiBrain,
    TACOminiHarness,
    TACOminiRAG,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_gt(techs=("T1078", "T1190"), missing=("mfa", "waf")) -> dict:
    return {
        "techniques": list(techs),
        "controls_missing": list(missing),
        "technique_validation": [{"technique": t, "valid": True} for t in techs],
    }


def _make_arch_dir(tmp_path: Path, arch_name: str, gt: Optional[dict] = None) -> Path:
    arch_dir = tmp_path / arch_name
    arch_dir.mkdir()
    if gt is not None:
        (arch_dir / "ground_truth.json").write_text(json.dumps(gt))
    return arch_dir


def _mock_threat_graph(hit: bool = True, techs=("T1078",), controls=("mfa",)):
    g = MagicMock()
    g.query.return_value = "some answer text" if hit else None
    g.attack_paths = {
        "ap1": MagicMock(arch="test_arch", techniques=list(techs))
    }
    g.arch_controls_missing = {"test_arch": list(controls)}
    return g


# ---------------------------------------------------------------------------
# TACOminiRAG class attributes
# ---------------------------------------------------------------------------

def test_rag_mini_class_attrs():
    mini = TACOminiRAG()
    assert mini.hop_type == "rag"
    assert mini.component == "TAWorkspace"
    assert mini.is_deterministic is True


# ---------------------------------------------------------------------------
# Confidence on graph hit / miss
# ---------------------------------------------------------------------------

def test_rag_graph_hit_confidence_080(tmp_path):
    gt = _make_gt()
    _make_arch_dir(tmp_path, "test_arch", gt)
    mini = TACOminiRAG(report_dir=tmp_path)
    ctx = TACOContext(query="threats?", arch_name="test_arch")

    with patch("chatbot.modules.taco_agent.TACOminiRAG._get_graph",
               return_value=_mock_threat_graph(hit=True)):
        hop = mini.run(ctx)

    assert hop.confidence == 0.80


def test_rag_graph_miss_confidence_050(tmp_path):
    gt = _make_gt()
    _make_arch_dir(tmp_path, "test_arch", gt)
    mini = TACOminiRAG(report_dir=tmp_path)
    ctx = TACOContext(query="threats?", arch_name="test_arch")

    with patch("chatbot.modules.taco_agent.TACOminiRAG._get_graph",
               return_value=_mock_threat_graph(hit=False)):
        hop = mini.run(ctx)

    assert hop.confidence == 0.50


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

def test_rag_no_arch_name_returns_miss():
    mini = TACOminiRAG()
    ctx = TACOContext(query="threats?", arch_name=None)
    hop = mini.run(ctx)
    assert hop.confidence == 0.50
    assert hop.hop_type == "rag"


def test_rag_missing_arch_dir_returns_miss(tmp_path):
    mini = TACOminiRAG(report_dir=tmp_path)
    ctx = TACOContext(query="threats?", arch_name="nonexistent_arch")
    hop = mini.run(ctx)
    assert hop.confidence == 0.50


def test_rag_exception_returns_zero_confidence(tmp_path):
    gt = _make_gt()
    _make_arch_dir(tmp_path, "test_arch", gt)
    mini = TACOminiRAG(report_dir=tmp_path)
    ctx = TACOContext(query="threats?", arch_name="test_arch")

    with patch("chatbot.modules.taco_agent.TACOminiRAG._get_graph",
               side_effect=RuntimeError("boom")):
        hop = mini.run(ctx)

    assert hop.confidence == 0.0
    assert "error" in hop.metadata


# ---------------------------------------------------------------------------
# Graph caching
# ---------------------------------------------------------------------------

def test_rag_graph_cached_single_build(tmp_path):
    gt = _make_gt()
    _make_arch_dir(tmp_path, "test_arch", gt)
    mini = TACOminiRAG(report_dir=tmp_path)
    ctx = TACOContext(query="threats?", arch_name="test_arch")

    mock_g = _mock_threat_graph()
    with patch("chatbot.modules.graph_index.ThreatGraph") as MockTG:
        MockTG.build.return_value = mock_g
        mini.run(ctx)
        mini.run(ctx)

    assert MockTG.build.call_count == 1


def test_rag_graph_rebuilt_on_arch_change(tmp_path):
    for arch in ("arch_a", "arch_b"):
        gt = _make_gt()
        _make_arch_dir(tmp_path, arch, gt)

    mini = TACOminiRAG(report_dir=tmp_path)
    ctx_a = TACOContext(query="threats?", arch_name="arch_a")
    ctx_b = TACOContext(query="threats?", arch_name="arch_b")

    mock_g = _mock_threat_graph()
    with patch("chatbot.modules.graph_index.ThreatGraph") as MockTG:
        MockTG.build.return_value = mock_g
        mini.run(ctx_a)
        mini.run(ctx_b)

    assert MockTG.build.call_count == 2


# ---------------------------------------------------------------------------
# Metadata structure
# ---------------------------------------------------------------------------

def test_rag_metadata_has_hit_techniques_controls(tmp_path):
    gt = _make_gt()
    _make_arch_dir(tmp_path, "test_arch", gt)
    mini = TACOminiRAG(report_dir=tmp_path)
    ctx = TACOContext(query="threats?", arch_name="test_arch")

    with patch("chatbot.modules.taco_agent.TACOminiRAG._get_graph",
               return_value=_mock_threat_graph(hit=True)):
        hop = mini.run(ctx)

    assert "had_hit" in hop.metadata
    assert "techniques" in hop.metadata
    assert "missing_controls" in hop.metadata


def test_rag_hop_record_all_fields_populated(tmp_path):
    gt = _make_gt()
    _make_arch_dir(tmp_path, "test_arch", gt)
    mini = TACOminiRAG(report_dir=tmp_path)
    ctx = TACOContext(query="what are the threats?", arch_name="test_arch")

    with patch("chatbot.modules.taco_agent.TACOminiRAG._get_graph",
               return_value=_mock_threat_graph(hit=True)):
        hop = mini.run(ctx)

    assert hop.hop_id
    assert hop.hop_type == "rag"
    assert hop.component == "TAWorkspace"
    assert hop.query_summary
    assert hop.response_summary
    assert hop.duration_ms >= 0
    assert hop.timestamp


# ---------------------------------------------------------------------------
# TACOAgent Phase 3 routing
# ---------------------------------------------------------------------------

def test_agent_default_includes_rag_mini():
    with patch("chatbot.modules.taco_agent.TACOminiRAG._get_graph", return_value=None):
        agent = TACOAgent()
    assert "rag" in agent.minis


def test_agent_rag_hop_runs_after_brain():
    with patch("chatbot.modules.ta_brain_query.query_brain",
               return_value={"confidence": 0.80, "had_match": True, "patterns_fired": [],
                             "arch_type": "test", "cache_route": "cache_hit", "predictions": {}}):
        with patch("chatbot.modules.taco_agent.TACOminiRAG._get_graph", return_value=None):
            agent = TACOAgent()
            chain = agent.run("threats?", arch_name="test_arch")

    assert chain.hops[0].hop_type == "brain"
    assert chain.hops[1].hop_type == "rag"


def test_agent_best_confidence_gates_escalation(tmp_path):
    """RAG conf=0.80 prevents harness even when brain conf=0.30."""
    brain_result = {"confidence": 0.30, "had_match": True, "patterns_fired": [],
                    "arch_type": "test", "cache_route": "new", "predictions": {}}
    mock_g = _mock_threat_graph(hit=True)

    with patch("chatbot.modules.ta_brain_query.query_brain", return_value=brain_result):
        with patch("chatbot.modules.taco_agent.TACOminiRAG._get_graph", return_value=mock_g):
            agent = TACOAgent(threshold=0.65)
            chain = agent.run("threats?", arch_name="test_arch", arch_mmd="graph TD\n  A --> B")

    hop_types = [h.hop_type for h in chain.hops]
    assert "harness" not in hop_types
    assert chain.routed_to_harness is False


def test_agent_routed_to_rag_flag():
    with patch("chatbot.modules.ta_brain_query.query_brain",
               return_value={"confidence": 0.80, "had_match": True, "patterns_fired": [],
                             "arch_type": "test", "cache_route": "cache_hit", "predictions": {}}):
        with patch("chatbot.modules.taco_agent.TACOminiRAG._get_graph", return_value=None):
            agent = TACOAgent()
            chain = agent.run("threats?", arch_name="test_arch")

    assert chain.routed_to_rag is True


def test_agent_no_rag_mini_works_as_phase2():
    """TACOAgent with explicit minis dict (no rag) still works correctly."""
    with patch("chatbot.modules.ta_brain_query.query_brain",
               return_value={"confidence": 0.80, "had_match": True, "patterns_fired": [],
                             "arch_type": "test", "cache_route": "cache_hit", "predictions": {}}):
        agent = TACOAgent(minis={"brain": TACOminiBrain(), "harness": TACOminiHarness()})
        chain = agent.run("threats?", arch_name="test_arch")

    assert "rag" not in agent.minis
    assert chain.routed_to_rag is False
    assert len(chain.hops) == 1
    assert chain.hops[0].hop_type == "brain"
