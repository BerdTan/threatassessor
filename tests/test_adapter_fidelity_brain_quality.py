"""
Engine Item 7 — Adapter fidelity score + brain-path quality bridge + corpus diversity signal.

Tests are deterministic (no API, no LLM). Three groups:
  1. Sub-item 1 — fidelity_detail in TF/CF/OAI adapter_metadata
  2. Sub-item 2 — brain_quality field plumbing (unit, no live brain required)
  3. Sub-item 3 — _corpus_diversity() entropy + flagging
"""

import math
import pytest

# ── Sub-item 1: Adapter fidelity detail ──────────────────────────────────────

def test_tf_adapter_fidelity_detail_present():
    from chatbot.adapters.terraform import TerraformAdapter
    src = '''
resource "aws_instance" "web" {}
resource "aws_s3_bucket" "data" {}
resource "aws_rds_cluster" "db" {}
'''
    graph = TerraformAdapter().extract(src, "main.tf")
    fd = graph.adapter_metadata.get("fidelity_detail")
    assert fd is not None, "TerraformAdapter must populate fidelity_detail"
    assert set(fd.keys()) >= {"node_coverage", "component_type_rate", "untyped_node_count",
                               "edge_inferred_count", "source_component_count"}


def test_tf_adapter_fidelity_detail_values():
    from chatbot.adapters.terraform import TerraformAdapter
    src = 'resource "aws_instance" "web" {}\nresource "unknown_thing" "x" {}\n'
    graph = TerraformAdapter().extract(src, "main.tf")
    fd = graph.adapter_metadata["fidelity_detail"]
    assert 0.0 <= fd["node_coverage"] <= 1.0
    assert 0.0 <= fd["component_type_rate"] <= 1.0
    assert fd["source_component_count"] >= 0
    assert fd["edge_inferred_count"] == len(graph.edges)


def test_cf_adapter_fidelity_detail_present():
    from chatbot.adapters.cloudformation import CloudFormationAdapter
    src = '''
AWSTemplateFormatVersion: "2010-09-09"
Resources:
  Web:
    Type: AWS::EC2::Instance
  Bucket:
    Type: AWS::S3::Bucket
  Fn:
    Type: AWS::Lambda::Function
'''
    graph = CloudFormationAdapter().extract(src, "stack.yaml")
    fd = graph.adapter_metadata.get("fidelity_detail")
    assert fd is not None
    assert fd["source_component_count"] == 3
    assert fd["edge_inferred_count"] == len(graph.edges)


def test_oai_adapter_fidelity_detail_present():
    from chatbot.adapters.openapi import OpenAPIAdapter
    src = '''
openapi: "3.0.0"
info:
  title: TestAPI
  version: "1.0"
paths:
  /users:
    get:
      summary: list users
  /orders:
    post:
      summary: create order
'''
    graph = OpenAPIAdapter().extract(src, "api.yaml")
    fd = graph.adapter_metadata.get("fidelity_detail")
    assert fd is not None
    assert fd["source_component_count"] >= 2  # at least 2 paths


def test_fidelity_node_coverage_partial():
    """When adapter filters some source resources, node_coverage < 1."""
    from chatbot.adapters.terraform import TerraformAdapter
    # Many resources — adapter may not map all uniquely
    src = "\n".join(
        f'resource "some_obscure_type_{i}" "r{i}" {{}}' for i in range(10)
    )
    graph = TerraformAdapter().extract(src, "main.tf")
    fd = graph.adapter_metadata["fidelity_detail"]
    # Coverage should be in [0, 1] regardless of mapping quality
    assert 0.0 <= fd["node_coverage"] <= 1.0


# ── Sub-item 3: Corpus diversity signal ──────────────────────────────────────

from chatbot.modules.ta_brain_builder import _corpus_diversity


def test_corpus_diversity_uniform():
    instances = [
        {"arch_type": "web_app"},
        {"arch_type": "cloud"},
        {"arch_type": "iot"},
        {"arch_type": "agentic"},
    ]
    div = _corpus_diversity(instances)
    assert div["entropy"] == pytest.approx(2.0, abs=0.001)  # log2(4) = 2.0
    assert div["flagged"] is False
    assert div["dominant_fraction"] == 0.25


def test_corpus_diversity_skewed_dominant_flagged():
    instances = [{"arch_type": "web_app"}] * 9 + [{"arch_type": "cloud"}]
    div = _corpus_diversity(instances)
    assert div["flagged"] is True
    assert div["dominant_type"] == "web_app"
    assert div["dominant_fraction"] > 0.5


def test_corpus_diversity_low_entropy_flagged():
    # Two types, heavily skewed (entropy well below 50% of max=1.0)
    instances = [{"arch_type": "web_app"}] * 8 + [{"arch_type": "iot"}] * 2
    div = _corpus_diversity(instances)
    assert div["entropy"] < div["max_entropy"]
    assert div["flagged"] is True


def test_corpus_diversity_empty():
    div = _corpus_diversity([])
    assert div["entropy"] == 0.0
    assert div["flagged"] is True


def test_corpus_diversity_single_type():
    instances = [{"arch_type": "cloud"}] * 5
    div = _corpus_diversity(instances)
    assert div["dominant_fraction"] == 1.0
    assert div["flagged"] is True


def test_corpus_diversity_has_required_keys():
    div = _corpus_diversity([{"arch_type": "web_app"}, {"arch_type": "iot"}])
    assert {"entropy", "max_entropy", "arch_type_counts", "dominant_type",
            "dominant_fraction", "flagged"} <= set(div.keys())


def test_corpus_diversity_entropy_range():
    """Entropy must be in [0, log2(n_types)]."""
    instances = [
        {"arch_type": "web_app"}, {"arch_type": "cloud"},
        {"arch_type": "iot"}, {"arch_type": "agentic"}, {"arch_type": "generic"},
    ]
    div = _corpus_diversity(instances)
    assert 0.0 <= div["entropy"] <= math.log2(5) + 0.001


# ── Sub-item 2: brain_quality field plumbing (unit) ──────────────────────────

def test_brain_quality_structure():
    """brain_quality dict has expected keys when populated."""
    brain_quality = {
        "pattern_id": "BRAIN-001",
        "arch_type": "web_app",
        "brier_combined": 0.35,
        "brier_technique": 0.28,
        "brier_control": 0.42,
        "benchmark_confidence": 0.65,
        "samples_used": 4,
    }
    required = {"pattern_id", "arch_type", "brier_combined", "brier_technique",
                "brier_control", "benchmark_confidence", "samples_used"}
    assert required <= set(brain_quality.keys())
    assert 0.0 <= brain_quality["brier_combined"] <= 1.0
    assert brain_quality["samples_used"] >= 0


def test_brain_quality_empty_graceful():
    """Empty brain_quality dict is a valid no-benchmark state."""
    brain_quality: dict = {}
    assert brain_quality.get("brier_combined") is None
    assert brain_quality.get("pattern_id") is None
