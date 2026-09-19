"""
Unit tests for adapter fidelity score (Engine Item 7.1).

Verifies that each adapter sets ArchitectureGraph.fidelity correctly:
- Terraform/CF/OAI: fidelity = nodes_produced / raw_source_count
- MMD: always 1.0 (lossless)
- Prose LLM: 0.8; Prose fallback: 0.3
"""

import json
import pytest

from chatbot.adapters.base import ArchitectureGraph
from chatbot.adapters.terraform import TerraformAdapter
from chatbot.adapters.cloudformation import CloudFormationAdapter
from chatbot.adapters.openapi import OpenAPIAdapter
from chatbot.adapters.mermaid import MermaidAdapter


# ── helpers ───────────────────────────────────────────────────────────────────

_TF_THREE_RESOURCES = """\
resource "aws_lambda_function" "api" {}
resource "aws_s3_bucket" "data" {}
resource "aws_dynamodb_table" "db" {}
"""

_CF_THREE = json.dumps({
    "AWSTemplateFormatVersion": "2010-09-09",
    "Resources": {
        "Lambda": {"Type": "AWS::Lambda::Function", "Properties": {}},
        "Bucket": {"Type": "AWS::S3::Bucket", "Properties": {}},
        "VPC":    {"Type": "AWS::EC2::VPC", "Properties": {}},
    },
})

_OAI_SPEC = json.dumps({
    "openapi": "3.0.0",
    "info": {"title": "Test", "version": "1"},
    "paths": {"/users": {"get": {}}, "/orders": {"get": {}}},
    "components": {
        "schemas": {"User": {}, "Order": {}},
        "securitySchemes": {"Bearer": {"type": "http"}},
    },
})

_MMD_SIMPLE = "flowchart LR\n  A[Service] --> B[(DB)]\n  A --> C([Ext])\n"


# ── ArchitectureGraph field defaults ──────────────────────────────────────────

def test_architecture_graph_defaults():
    g = ArchitectureGraph(title="t", source_format="unknown")
    assert g.fidelity == 1.0
    assert g.source_component_count == 0


def test_architecture_graph_fidelity_bounds():
    with pytest.raises(Exception):
        ArchitectureGraph(title="t", source_format="x", fidelity=1.5)
    with pytest.raises(Exception):
        ArchitectureGraph(title="t", source_format="x", fidelity=-0.1)


# ── Terraform ─────────────────────────────────────────────────────────────────

def test_terraform_fidelity_full():
    g = TerraformAdapter().extract(_TF_THREE_RESOURCES, "main.tf")
    assert g.source_component_count == 3
    assert g.fidelity == pytest.approx(1.0)


def test_terraform_fidelity_stored_in_graph():
    g = TerraformAdapter().extract(_TF_THREE_RESOURCES, "main.tf")
    assert 0.0 <= g.fidelity <= 1.0


def test_terraform_empty_file():
    g = TerraformAdapter().extract("", "empty.tf")
    assert g.fidelity == 1.0  # 0/max(1,0) → capped at 1.0
    assert g.source_component_count == 0


# ── CloudFormation ────────────────────────────────────────────────────────────

def test_cloudformation_fidelity_full():
    g = CloudFormationAdapter().extract(_CF_THREE, "stack.json")
    assert g.source_component_count == 3
    assert g.fidelity == pytest.approx(1.0)


def test_cloudformation_empty_template():
    g = CloudFormationAdapter().extract(
        json.dumps({"AWSTemplateFormatVersion": "2010-09-09", "Resources": {}}),
        "empty.json",
    )
    assert g.fidelity == pytest.approx(1.0)
    assert g.source_component_count == 0


# ── OpenAPI ───────────────────────────────────────────────────────────────────

def test_openapi_fidelity_full():
    g = OpenAPIAdapter().extract(_OAI_SPEC, "api.json")
    # raw = 2 paths + 2 schemas + 1 securityScheme = 5; nodes should cover all
    assert g.source_component_count == 5
    assert 0.0 < g.fidelity <= 1.0


def test_openapi_fidelity_range():
    g = OpenAPIAdapter().extract(_OAI_SPEC, "api.json")
    assert 0.0 <= g.fidelity <= 1.0


def test_openapi_empty_spec():
    spec = json.dumps({"openapi": "3.0.0", "info": {"title": "T", "version": "1"}})
    g = OpenAPIAdapter().extract(spec, "empty.json")
    assert g.fidelity == pytest.approx(1.0)


# ── Mermaid ───────────────────────────────────────────────────────────────────

def test_mermaid_fidelity_always_one():
    g = MermaidAdapter().extract(_MMD_SIMPLE, "arch.mmd")
    assert g.fidelity == pytest.approx(1.0)


def test_mermaid_source_component_count_matches_nodes():
    g = MermaidAdapter().extract(_MMD_SIMPLE, "arch.mmd")
    assert g.source_component_count == len(g.nodes)


# ── Prose ─────────────────────────────────────────────────────────────────────

def test_prose_fidelity_fallback(monkeypatch):
    from chatbot.adapters import prose
    monkeypatch.setattr(prose, "_call_llm", lambda _text: None)
    from chatbot.adapters.prose import ProseAdapter
    g = ProseAdapter().extract(
        "A web service connects to a database and an external API.", "arch.txt"
    )
    assert g.fidelity == pytest.approx(0.3)
    assert g.adapter_metadata["extraction_method"] == "keyword_fallback"


def test_prose_fidelity_llm(monkeypatch):
    from chatbot.adapters import prose
    monkeypatch.setattr(prose, "_call_llm", lambda _text: {
        "title": "Test",
        "nodes": [
            {"id": "svc", "label": "Service", "type": "service"},
            {"id": "db",  "label": "Database", "type": "database"},
        ],
        "edges": [{"source": "svc", "target": "db"}],
    })
    from chatbot.adapters.prose import ProseAdapter
    g = ProseAdapter().extract("some text", "arch.txt")
    assert g.fidelity == pytest.approx(0.8)
    assert g.adapter_metadata["extraction_method"] == "llm"
