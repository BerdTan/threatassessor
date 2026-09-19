"""
Unit tests for Engine Item 10 — propagation/taint layer.

Covers:
  10.1 — ArchNode.provenance + ArchitectureGraph.pipeline_mode fields
  10.2 — pipeline_provenance in brain instance from routing_mode in ground_truth
  10.3 — generated_by + pipeline_mode in TAExportBundle architecture/assessment
  10.4 — cross_agent_provenance in query_brain() return values
"""

import pytest
from unittest.mock import MagicMock, patch


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_graph(provenance="adapter", node_count=3, pipeline_mode=None):
    from chatbot.adapters.base import ArchitectureGraph, ArchNode
    nodes = [ArchNode(id=f"n{i}", label=f"Node {i}", node_type="service", provenance=provenance)
             for i in range(node_count)]
    return ArchitectureGraph(
        title="test",
        nodes=nodes,
        edges=[],
        pipeline_mode=pipeline_mode,
    )


# ── 10.1: ArchNode.provenance field ──────────────────────────────────────────

def test_archnode_provenance_default_is_none():
    from chatbot.adapters.base import ArchNode
    n = ArchNode(id="n1", label="Node 1", node_type="service")
    assert n.provenance is None


def test_archnode_provenance_adapter():
    from chatbot.adapters.base import ArchNode
    n = ArchNode(id="n1", label="Node 1", node_type="service", provenance="adapter")
    assert n.provenance == "adapter"


def test_archnode_provenance_synthetic():
    from chatbot.adapters.base import ArchNode
    n = ArchNode(id="n1", label="Node 1", node_type="service", provenance="synthetic")
    assert n.provenance == "synthetic"


def test_archnode_provenance_brain_enriched():
    from chatbot.adapters.base import ArchNode
    n = ArchNode(id="n1", label="Node 1", node_type="service", provenance="brain_enriched")
    assert n.provenance == "brain_enriched"


def test_archnode_provenance_taclaw():
    from chatbot.adapters.base import ArchNode
    n = ArchNode(id="n1", label="Node 1", node_type="service", provenance="taclaw")
    assert n.provenance == "taclaw"


# ── 10.1: ArchitectureGraph.pipeline_mode field ───────────────────────────────

def test_architecture_graph_pipeline_mode_default_is_none():
    from chatbot.adapters.base import ArchitectureGraph
    g = ArchitectureGraph(title="t", nodes=[], edges=[])
    assert g.pipeline_mode is None


def test_architecture_graph_pipeline_mode_settable():
    from chatbot.adapters.base import ArchitectureGraph
    g = ArchitectureGraph(title="t", nodes=[], edges=[], pipeline_mode="full_moe")
    assert g.pipeline_mode == "full_moe"


def test_architecture_graph_pipeline_mode_api_only():
    from chatbot.adapters.base import ArchitectureGraph
    g = ArchitectureGraph(title="t", nodes=[], edges=[], pipeline_mode="api_only")
    assert g.pipeline_mode == "api_only"


# ── 10.1: NodeProvenance type alias exported ─────────────────────────────────

def test_nodeprovenance_type_exported():
    from chatbot.adapters.base import NodeProvenance
    assert NodeProvenance is not None


# ── 10.1: Adapters set provenance="adapter" ───────────────────────────────────

def test_mermaid_adapter_sets_provenance():
    from chatbot.adapters.mermaid import MermaidAdapter
    mmd = b"flowchart LR\n    A[Service] --> B[(DB)]"
    adapter = MermaidAdapter()
    graph = adapter.extract(mmd, "test.mmd")
    assert all(n.provenance == "adapter" for n in graph.nodes)


def test_terraform_adapter_sets_provenance():
    from chatbot.adapters.terraform import TerraformAdapter
    tf = b'resource "aws_lambda_function" "handler" {}\nresource "aws_s3_bucket" "data" {}'
    adapter = TerraformAdapter()
    graph = adapter.extract(tf, "main.tf")
    assert all(n.provenance == "adapter" for n in graph.nodes)


def test_cloudformation_adapter_sets_provenance():
    from chatbot.adapters.cloudformation import CloudFormationAdapter
    cfn = b"""
AWSTemplateFormatVersion: '2010-09-09'
Resources:
  MyLambda:
    Type: AWS::Lambda::Function
    Properties: {}
  MyBucket:
    Type: AWS::S3::Bucket
"""
    adapter = CloudFormationAdapter()
    graph = adapter.extract(cfn, "template.yaml")
    assert all(n.provenance == "adapter" for n in graph.nodes)


# ── 10.2: pipeline_provenance in brain instance ───────────────────────────────

def test_extract_instance_includes_pipeline_provenance(tmp_path):
    """extract_instance() reads routing_mode from ground_truth.metadata and stores it."""
    import json
    from chatbot.modules.ta_brain_builder import extract_instance

    # Build a minimal arch_dir with required files
    arch_dir = tmp_path / "test_arch"
    arch_dir.mkdir()

    gt = {
        "metadata": {
            "architecture_type": "web_app",
            "node_count": 4,
            "edge_count": 3,
            "run_ts": "2026-09-19T00:00:00Z",
            "parsed_nodes": {"n1": {"shape": "rect"}, "n2": {"shape": "cylinder"}},
            "parsed_edges": [{"source": "n1", "target": "n2"}],
            "generated_by": "parser",
            "routing_mode": "full_moe",
        },
        "techniques": ["T1059", "T1190"],
        "confidence": 0.85,
    }
    gs = {
        "aivss": {"overall": {"composite": 6.5, "severity": "HIGH"}},
        "exploitation": {"blocked": False},
    }
    (arch_dir / "ground_truth.json").write_text(json.dumps(gt))
    (arch_dir / "governance_signals.json").write_text(json.dumps(gs))

    inst = extract_instance(arch_dir)
    assert inst is not None
    assert inst["pipeline_provenance"] == "full_moe"


def test_extract_instance_pipeline_provenance_unknown_when_absent(tmp_path):
    """routing_mode absent → pipeline_provenance='unknown'."""
    import json
    from chatbot.modules.ta_brain_builder import extract_instance

    arch_dir = tmp_path / "test_arch2"
    arch_dir.mkdir()

    gt = {
        "metadata": {
            "architecture_type": "generic",
            "node_count": 3,
            "edge_count": 2,
            "run_ts": "2026-09-19T00:00:00Z",
            "parsed_nodes": {"n1": {"shape": "rect"}},
            "parsed_edges": [],
            "generated_by": "parser",
            # no routing_mode
        },
        "techniques": ["T1059"],
        "confidence": 0.80,
    }
    gs = {
        "aivss": {"overall": {"composite": 5.0, "severity": "MEDIUM"}},
        "exploitation": {"blocked": False},
    }
    (arch_dir / "ground_truth.json").write_text(json.dumps(gt))
    (arch_dir / "governance_signals.json").write_text(json.dumps(gs))

    inst = extract_instance(arch_dir)
    assert inst is not None
    assert inst["pipeline_provenance"] == "unknown"


# ── 10.2: AnalysisStage stamps routing_mode into ground_truth.metadata ────────

def test_analysis_stage_stamps_routing_mode():
    """routing_mode in ctx → stamped into ctx['ground_truth']['metadata']."""
    from chatbot.harness.stages import AnalysisStage
    from chatbot.harness.controller import PipelineContext
    from unittest.mock import MagicMock, patch

    stage = AnalysisStage()
    mock_result = MagicMock()
    mock_result.data = {
        "analysis": {"metadata": {"generated_by": "parser"}, "confidence": 0.9},
        "confidence": 0.9,
        "patterns_applied": [],
    }

    ctx = PipelineContext({
        "architecture_path": "test.mmd",
        "report_dir": "/tmp/report",
        "routing_mode": "full_moe",
        "_source_trust": "verified",
        "include_validation": False,
        "ssp_profile": "low_risk_cloud",
        "enable_ssp": True,
    })

    with patch("chatbot.services.ThreatAnalysisService") as MockSvc:
        MockSvc.return_value.safe_execute.return_value = mock_result
        stage._logic(ctx)

    assert ctx["ground_truth"]["metadata"]["routing_mode"] == "full_moe"
    assert ctx["ground_truth"]["metadata"]["source_trust"] == "verified"


def test_analysis_stage_no_routing_mode_no_stamp():
    """routing_mode absent → metadata left unchanged."""
    from chatbot.harness.stages import AnalysisStage
    from chatbot.harness.controller import PipelineContext

    stage = AnalysisStage()
    mock_result = MagicMock()
    mock_result.data = {
        "analysis": {"metadata": {"generated_by": "parser"}},
        "confidence": 0.9,
        "patterns_applied": [],
    }

    ctx = PipelineContext({
        "architecture_path": "test.mmd",
        "report_dir": "/tmp/report",
        "include_validation": False,
        "ssp_profile": "low_risk_cloud",
        "enable_ssp": True,
    })

    with patch("chatbot.services.ThreatAnalysisService") as MockSvc:
        MockSvc.return_value.safe_execute.return_value = mock_result
        stage._logic(ctx)

    # routing_mode absent → should NOT be stamped
    assert "routing_mode" not in ctx["ground_truth"]["metadata"]


# ── 10.3: TAExportBundle architecture + assessment carry pipeline provenance ──

def test_export_architecture_includes_generated_by():
    from chatbot.modules.ta_exporter import _build_architecture
    gt = {"metadata": {"generated_by": "parser+llm", "routing_mode": "full_moe", "source_trust": "verified"}}
    arch = _build_architecture("test_arch", gt)
    assert arch["generated_by"] == "parser+llm"


def test_export_architecture_includes_pipeline_mode():
    from chatbot.modules.ta_exporter import _build_architecture
    gt = {"metadata": {"generated_by": "parser", "routing_mode": "api_only"}}
    arch = _build_architecture("test_arch", gt)
    assert arch["pipeline_mode"] == "api_only"


def test_export_architecture_pipeline_mode_defaults_api_only():
    from chatbot.modules.ta_exporter import _build_architecture
    gt = {"metadata": {"generated_by": "parser"}}  # no routing_mode
    arch = _build_architecture("test_arch", gt)
    assert arch["pipeline_mode"] == "api_only"


def test_export_architecture_includes_source_trust():
    from chatbot.modules.ta_exporter import _build_architecture
    gt = {"metadata": {"source_trust": "verified"}}
    arch = _build_architecture("test_arch", gt)
    assert arch["source_trust"] == "verified"


def test_export_assessment_includes_pipeline_mode():
    from chatbot.modules.ta_exporter import _build_assessment
    gt = {
        "metadata": {"routing_mode": "full_moe", "generated_by": "parser+llm"},
        "attack_paths": [],
        "techniques": [],
        "control_recommendations": [],
    }
    assessment = _build_assessment(gt)
    assert assessment["pipeline_mode"] == "full_moe"
    assert assessment["generated_by"] == "parser+llm"


def test_export_assessment_pipeline_mode_default():
    from chatbot.modules.ta_exporter import _build_assessment
    gt = {
        "metadata": {},
        "attack_paths": [],
        "techniques": [],
        "control_recommendations": [],
    }
    assessment = _build_assessment(gt)
    assert assessment["pipeline_mode"] == "api_only"


# ── 10.4: cross_agent_provenance in query_brain() ────────────────────────────

def test_query_brain_infer_returns_cross_agent_provenance_on_cache_hit(tmp_path):
    """Cache hit path returns cross_agent_provenance with source=brain."""
    from chatbot.modules.ta_brain_query import query_brain

    brain = {
        "pattern_version": 1,
        "patterns": [],
        "gaps": [],
        "meta": {},
    }
    cache_response = {
        "had_match": True,
        "patterns_fired": ["pat_001"],
        "confidence": 0.85,
        "predictions": {"techniques": ["T1059"]},
    }

    with patch("chatbot.modules.ta_brain_query._load_brain", return_value=brain), \
         patch("chatbot.modules.ta_brain_query._find_instance", return_value={
             "topology_signature": "abc123", "arch_type": "web_app"
         }), \
         patch("chatbot.modules.ta_brain_query.get_cache_manager") as mock_cm, \
         patch("chatbot.modules.ta_brain_query._log_interaction"):
        mock_cache = MagicMock()
        mock_cache.route.return_value = ("hit", cache_response, "cache_hit")
        mock_cm.return_value = mock_cache

        result = query_brain(mode="infer", arch_name="03_aws_3tier", caller_type="mcp")

    cap = result.get("cross_agent_provenance", {})
    assert cap.get("source") == "brain"
    assert cap.get("query_mode") == "infer"
    assert cap.get("caller_type") == "mcp"
    assert cap.get("data_origin") == "cache"


def test_query_brain_infer_returns_cross_agent_provenance_on_kg_miss(tmp_path):
    """KG match path returns cross_agent_provenance with data_origin=kg_match."""
    from chatbot.modules.ta_brain_query import query_brain

    brain = {
        "pattern_version": 1,
        "patterns": [],
        "gaps": [],
        "meta": {},
    }
    kg_result = {
        "had_match": False,
        "patterns_fired": [],
        "confidence": 0.0,
        "predictions": {},
        "evidence": {},
    }

    with patch("chatbot.modules.ta_brain_query._load_brain", return_value=brain), \
         patch("chatbot.modules.ta_brain_query._find_instance", return_value={
             "topology_signature": "def456", "arch_type": "generic"
         }), \
         patch("chatbot.modules.ta_brain_query.get_cache_manager") as mock_cm, \
         patch("chatbot.modules.ta_brain_query._run_infer", return_value=kg_result), \
         patch("chatbot.modules.ta_brain_query._log_interaction"), \
         patch("chatbot.modules.ta_brain_query.extract_shape_counts", return_value={}):
        mock_cache = MagicMock()
        mock_cache.route.return_value = ("miss", None, "new")
        mock_cm.return_value = mock_cache

        result = query_brain(mode="infer", arch_name="07_gcp_serverless", caller_type="rest")

    cap = result.get("cross_agent_provenance", {})
    assert cap.get("source") == "brain"
    assert cap.get("data_origin") == "kg_match"


def test_query_brain_gaps_returns_cross_agent_provenance():
    """Gaps mode returns cross_agent_provenance."""
    from chatbot.modules.ta_brain_query import query_brain

    brain = {"pattern_version": 1, "patterns": [], "gaps": [{"id": "g1"}], "meta": {}}

    with patch("chatbot.modules.ta_brain_query._load_brain", return_value=brain), \
         patch("chatbot.modules.ta_brain_query._log_interaction"):
        result = query_brain(mode="gaps", caller_type="harness")

    cap = result.get("cross_agent_provenance", {})
    assert cap.get("source") == "brain"
    assert cap.get("query_mode") == "gaps"
    assert cap.get("caller_type") == "harness"


def test_query_brain_patterns_returns_cross_agent_provenance():
    """Patterns mode returns cross_agent_provenance."""
    from chatbot.modules.ta_brain_query import query_brain

    brain = {"pattern_version": 2, "patterns": [{"id": "p1", "trigger": {"arch_type": "web_app"}}], "meta": {}}

    with patch("chatbot.modules.ta_brain_query._load_brain", return_value=brain), \
         patch("chatbot.modules.ta_brain_query._log_interaction"):
        result = query_brain(mode="patterns", caller_type="rest")

    cap = result.get("cross_agent_provenance", {})
    assert cap.get("source") == "brain"
    assert cap.get("query_mode") == "patterns"
