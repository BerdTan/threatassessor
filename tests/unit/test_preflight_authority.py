"""
Unit tests for Engine Item 9 — pre-flight authority layer.

Covers:
  9.1 — source_trust field on ArchitectureGraph
  9.2 — check_preflight() screener in InhouseGovernanceAdapter
  9.4 — BouncerStage second-signal (_preflight_blocked in ctx)
"""

import pytest

from chatbot.adapters.base import ArchitectureGraph, ArchNode, SourceTrust
from chatbot.harness.governance import InhouseGovernanceAdapter


# ── helpers ───────────────────────────────────────────────────────────────────

def _graph(source_trust: SourceTrust = "unverified", source_format: str = "terraform",
           node_count: int = 5, fidelity: float = 1.0) -> ArchitectureGraph:
    nodes = [ArchNode(id=f"n{i}", label=f"Node {i}", node_type="service") for i in range(node_count)]
    return ArchitectureGraph(
        title="test",
        nodes=nodes,
        edges=[],
        source_format=source_format,
        fidelity=fidelity,
        source_component_count=node_count,
        source_trust=source_trust,
    )


# ── 9.1: source_trust field ───────────────────────────────────────────────────

def test_source_trust_default_is_unverified():
    g = ArchitectureGraph(title="t", nodes=[], edges=[])
    assert g.source_trust == "unverified"


def test_source_trust_verified():
    g = _graph(source_trust="verified")
    assert g.source_trust == "verified"


def test_source_trust_adversarial():
    g = _graph(source_trust="adversarial")
    assert g.source_trust == "adversarial"


def test_source_trust_invalid_rejected():
    with pytest.raises(Exception):
        ArchitectureGraph(title="t", nodes=[], edges=[], source_trust="unknown_level")


# ── 9.2: check_preflight — pass cases ────────────────────────────────────────

def test_preflight_passes_clean_unverified():
    gov = InhouseGovernanceAdapter()
    sig = gov.check_preflight(_graph())
    assert sig.preflight["blocked"] is False
    assert sig.preflight["trust_level"] == "unverified"


def test_preflight_passes_verified():
    gov = InhouseGovernanceAdapter()
    sig = gov.check_preflight(_graph(source_trust="verified"))
    assert sig.preflight["blocked"] is False
    assert sig.preflight["trust_level"] == "verified"


def test_preflight_returns_governancesignals():
    from chatbot.harness.governance import GovernanceSignals
    gov = InhouseGovernanceAdapter()
    sig = gov.check_preflight(_graph())
    assert isinstance(sig, GovernanceSignals)


# ── 9.2: check_preflight — block cases ───────────────────────────────────────

def test_preflight_blocks_adversarial():
    gov = InhouseGovernanceAdapter()
    sig = gov.check_preflight(_graph(source_trust="adversarial"))
    assert sig.preflight["blocked"] is True
    assert sig.preflight["severity"] == "CRITICAL"
    assert "adversarial" in sig.preflight["reason"]


def test_preflight_block_reason_includes_format():
    gov = InhouseGovernanceAdapter()
    sig = gov.check_preflight(_graph(source_trust="adversarial", source_format="prose"))
    assert "prose" in sig.preflight["reason"]


# ── 9.2: check_preflight — warning cases ─────────────────────────────────────

def test_preflight_warns_oversized_graph():
    gov = InhouseGovernanceAdapter()
    sig = gov.check_preflight(_graph(node_count=501))
    assert sig.preflight["blocked"] is False
    assert sig.preflight["severity"] == "HIGH"
    assert any("oversized" in w for w in sig.preflight["warnings"])


def test_preflight_warns_low_fidelity_prose():
    gov = InhouseGovernanceAdapter()
    sig = gov.check_preflight(_graph(source_format="prose", fidelity=0.2))
    assert sig.preflight["blocked"] is False
    assert sig.preflight["severity"] in ("MEDIUM", "HIGH")
    assert any("fidelity" in w for w in sig.preflight["warnings"])


def test_preflight_no_warn_normal_prose_fidelity():
    gov = InhouseGovernanceAdapter()
    sig = gov.check_preflight(_graph(source_format="prose", fidelity=0.8))
    assert sig.preflight["blocked"] is False
    assert sig.preflight["warnings"] == []


def test_preflight_at_node_limit_no_warn():
    gov = InhouseGovernanceAdapter()
    sig = gov.check_preflight(_graph(node_count=500))
    assert not any("oversized" in w for w in sig.preflight["warnings"])


# ── 9.2: check_preflight — metadata fields ───────────────────────────────────

def test_preflight_includes_fidelity_and_node_count():
    gov = InhouseGovernanceAdapter()
    g = _graph(node_count=10, fidelity=0.9)
    sig = gov.check_preflight(g)
    assert sig.preflight["node_count"] == 10
    assert sig.preflight["fidelity"] == pytest.approx(0.9)


# ── 9.4: BouncerStage second-signal ──────────────────────────────────────────

def test_bouncer_blocks_when_preflight_blocked():
    from chatbot.harness.controller import BlockedPipelineError, PipelineContext
    from chatbot.harness.stages import BouncerStage

    ctx = PipelineContext({
        "architecture_path": "test.mmd",
        "report_dir": "/tmp/report",
        "governance_signals": {"exploitation": {"blocked": False}},
        "_outbound_blocked": False,
        "_preflight_blocked": True,
    })
    bouncer = BouncerStage()
    with pytest.raises(BlockedPipelineError) as exc_info:
        bouncer._logic(ctx)
    assert "preflight" in exc_info.value.reason


def test_bouncer_passes_when_preflight_false():
    from chatbot.harness.controller import PipelineContext
    from chatbot.harness.stages import BouncerStage

    ctx = PipelineContext({
        "architecture_path": "test.mmd",
        "report_dir": "/tmp/report",
        "governance_signals": {"exploitation": {"blocked": False}},
        "_outbound_blocked": False,
        "_preflight_blocked": False,
    })
    bouncer = BouncerStage()
    result = bouncer._logic(ctx)
    assert result is ctx


def test_bouncer_passes_when_no_preflight_key():
    """_preflight_blocked absent → no second-signal check (backward compat)."""
    from chatbot.harness.controller import PipelineContext
    from chatbot.harness.stages import BouncerStage

    ctx = PipelineContext({
        "architecture_path": "test.mmd",
        "report_dir": "/tmp/report",
        "governance_signals": {"exploitation": {"blocked": False}},
        "_outbound_blocked": False,
    })
    bouncer = BouncerStage()
    result = bouncer._logic(ctx)
    assert result is ctx


def test_bouncer_exploitation_still_blocks_independently():
    """exploitation.blocked=True still triggers independently of preflight."""
    from chatbot.harness.controller import BlockedPipelineError, PipelineContext
    from chatbot.harness.stages import BouncerStage

    ctx = PipelineContext({
        "architecture_path": "test.mmd",
        "report_dir": "/tmp/report",
        "governance_signals": {"exploitation": {"blocked": True}},
        "_outbound_blocked": False,
        "_preflight_blocked": False,
    })
    bouncer = BouncerStage()
    with pytest.raises(BlockedPipelineError) as exc_info:
        bouncer._logic(ctx)
    assert "exploitation" in exc_info.value.reason
