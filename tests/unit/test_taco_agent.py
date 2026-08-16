"""Tests for TACOAgent, TACOmini, HopRecord, HopChain (Phase 1 + refactor)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from chatbot.modules.taco_agent import (
    HopChain,
    HopRecord,
    TACOAgent,
    TACOContext,
    TACOmini,
    TACOminiBrain,
    TACOminiCritic,
    TACOminiHarness,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hop(hop_type: str = "brain", confidence: float = 0.80, duration_ms: int = 10) -> HopRecord:
    component = {"brain": "TABrain", "harness": "TAHarness", "critic": "TACritic"}[hop_type]
    return HopRecord(
        hop_id="test-id",
        hop_type=hop_type,
        component=component,
        query_summary="test query",
        response_summary="ok",
        confidence=confidence,
        duration_ms=duration_ms,
        timestamp="2026-08-15T00:00:00+00:00",
        metadata={},
    )


def _mock_mini(hop: HopRecord) -> TACOmini:
    """Return a TACOmini whose run() always returns the given hop."""
    m = MagicMock(spec=TACOmini)
    m.run.return_value = hop
    return m


def _brain_result_match(confidence: float = 0.80) -> dict:
    return {
        "had_match": True,
        "confidence": confidence,
        "patterns_fired": ["BRAIN-001"],
        "arch_type": "web_app",
        "cache_route": "kg",
        "predictions": {
            "techniques": ["T1190"],
            "detect_rules": ["DETECT-001"],
            "aivss_floor": 0.5,
            "aivss_mean": 0.6,
            "common_missing_controls": ["WAF"],
        },
    }


def _brain_result_error() -> dict:
    return {"error": "Brain not built."}


# ---------------------------------------------------------------------------
# 1. Serialization — Pydantic wire-safe roundtrip
# ---------------------------------------------------------------------------

def test_hoprecord_model_dump_json_roundtrip():
    rec = _hop("brain", 0.80)
    d = rec.model_dump()
    assert json.dumps(d)
    assert HopRecord.model_validate(d).hop_id == "test-id"


def test_hopchain_model_dump_json_roundtrip():
    chain = HopChain(
        chain_id="chain-1",
        query="test",
        arch_name="web_app",
        hops=[_hop("brain", 0.8)],
        final_confidence=0.8,
        final_response={},
        total_duration_ms=10,
        routed_to_harness=False,
        routed_to_critics=False,
        created_at="2026-08-15T00:00:00+00:00",
    )
    agent = TACOAgent()
    d = agent.to_dict(chain)
    assert json.dumps(d)
    restored = HopChain.model_validate(d)
    assert restored.chain_id == "chain-1"
    assert restored.hops[0].hop_type == "brain"


# ---------------------------------------------------------------------------
# 2. TACOmini base contract
# ---------------------------------------------------------------------------

def test_mini_is_deterministic_flags():
    assert TACOminiBrain.is_deterministic is True
    assert TACOminiHarness.is_deterministic is True


def test_mini_model_stored():
    brain = TACOminiBrain(model="haiku")
    harness = TACOminiHarness(model="sonnet")
    assert brain.model == "haiku"
    assert harness.model == "sonnet"


def test_mini_base_raises_not_implemented():
    mini = TACOmini()
    with pytest.raises(NotImplementedError):
        mini.run(TACOContext(query="test"))


# ---------------------------------------------------------------------------
# 3. Routing via injectable minis
# ---------------------------------------------------------------------------

def test_brain_only_when_confidence_above_threshold():
    agent = TACOAgent(
        threshold=0.65,
        minis={"brain": _mock_mini(_hop("brain", 0.90)), "harness": _mock_mini(_hop("harness", 0.80))},
    )
    chain = agent.run("test", arch_name="web_app", arch_mmd="graph TD; A-->B")
    assert chain.routed_to_harness is False
    assert len(chain.hops) == 1
    assert chain.hops[0].hop_type == "brain"


def test_brain_only_when_no_mmd_provided():
    agent = TACOAgent(
        threshold=0.65,
        minis={"brain": _mock_mini(_hop("brain", 0.30)), "harness": _mock_mini(_hop("harness", 0.80))},
    )
    chain = agent.run("test", arch_name="web_app", arch_mmd=None)
    assert chain.routed_to_harness is False
    assert len(chain.hops) == 1


def test_escalates_to_harness_when_low_conf_and_mmd():
    harness_mini = _mock_mini(_hop("harness", 0.75, duration_ms=300))
    agent = TACOAgent(
        threshold=0.65,
        minis={"brain": _mock_mini(_hop("brain", 0.40)), "harness": harness_mini},
    )
    chain = agent.run("test", arch_name="web_app", arch_mmd="graph TD; A-->B")
    assert chain.routed_to_harness is True
    assert len(chain.hops) == 2
    assert chain.hops[1].hop_type == "harness"
    assert chain.hops[1].routed is True


def test_total_duration_equals_sum_of_hop_durations():
    agent = TACOAgent(
        threshold=0.65,
        minis={
            "brain":   _mock_mini(_hop("brain",   0.30, duration_ms=12)),
            "harness": _mock_mini(_hop("harness", 0.75, duration_ms=350)),
        },
    )
    chain = agent.run("test", arch_name="web_app", arch_mmd="graph TD; A-->B")
    assert chain.total_duration_ms == 12 + 350


def test_custom_threshold_overrides_default():
    # conf=0.70 is above default 0.65 but below custom 0.90 — should escalate
    agent = TACOAgent(
        threshold=0.90,
        minis={
            "brain":   _mock_mini(_hop("brain",   0.70)),
            "harness": _mock_mini(_hop("harness", 0.80)),
        },
    )
    chain = agent.run("test", arch_name="web_app", arch_mmd="graph TD; A-->B")
    assert chain.routed_to_harness is True


# ---------------------------------------------------------------------------
# 4. TACOminiBrain integration (real query_brain call, mocked response)
# ---------------------------------------------------------------------------

def test_brain_mini_caller_type_is_taco_agent():
    with patch("chatbot.modules.ta_brain_query.query_brain") as mock_qb:
        mock_qb.return_value = _brain_result_match(0.90)
        mini = TACOminiBrain()
        mini.run(TACOContext(query="what are top threats?", arch_name="web_app"))
    called_kwargs = mock_qb.call_args.kwargs
    assert called_kwargs.get("caller_type") == "taco_agent"


def test_brain_mini_error_returns_zero_confidence():
    with patch("chatbot.modules.ta_brain_query.query_brain") as mock_qb:
        mock_qb.return_value = _brain_result_error()
        mini = TACOminiBrain()
        hop = mini.run(TACOContext(query="test", arch_name=None))
    assert hop.confidence == 0.0
    assert "error" in hop.response_summary


def test_brain_mini_populates_all_required_fields():
    with patch("chatbot.modules.ta_brain_query.query_brain") as mock_qb:
        mock_qb.return_value = _brain_result_match(0.80)
        mini = TACOminiBrain()
        hop = mini.run(TACOContext(query="test query", arch_name="web_app"))
    for field_name in ["hop_id", "hop_type", "component", "query_summary",
                       "response_summary", "duration_ms", "timestamp"]:
        assert getattr(hop, field_name) not in (None, ""), f"Field '{field_name}' empty"


# ---------------------------------------------------------------------------
# 5. TACOAgent._run_mini dispatch
# ---------------------------------------------------------------------------

def test_run_mini_dispatches_to_correct_mini():
    brain_mini = _mock_mini(_hop("brain", 0.90))
    agent = TACOAgent(minis={"brain": brain_mini, "harness": _mock_mini(_hop("harness", 0.80))})
    ctx = TACOContext(query="test")
    agent._run_mini("brain", ctx)
    brain_mini.run.assert_called_once_with(ctx)


def test_run_mini_raises_on_unknown_name():
    agent = TACOAgent()
    with pytest.raises(KeyError):
        agent._run_mini("nonexistent", TACOContext(query="test"))


# ---------------------------------------------------------------------------
# TACOminiCritic — Phase 4 (human-gated MoE hop)
# ---------------------------------------------------------------------------

def test_critic_not_in_default_agent():
    """Gate 1: critic_enabled defaults to false → not registered."""
    agent = TACOAgent()
    assert "critic" not in agent.minis


def test_critic_registered_when_injected():
    """Critic can be injected directly (bypasses settings gate for testing)."""
    critic = TACOminiCritic()
    agent = TACOAgent(minis={
        "brain":   _mock_mini(_hop("brain", 0.70)),
        "harness": _mock_mini(_hop("harness", 0.80)),
        "critic":  critic,
    })
    assert "critic" in agent.minis


def test_critic_not_run_without_force_flag():
    """Gate 2: even when registered, critic skips unless force_critic=True."""
    critic_mock = _mock_mini(_hop("critic", 0.90))
    agent = TACOAgent(minis={
        "brain":   _mock_mini(_hop("brain", 0.70)),
        "harness": _mock_mini(_hop("harness", 0.80)),
        "critic":  critic_mock,
    })
    chain = agent.run("what are the risks?", force_critic=False)
    critic_mock.run.assert_not_called()
    assert chain.routed_to_critics is False


def test_critic_runs_when_force_flag_set():
    """Gate 2 open: force_critic=True runs the critic and sets routed_to_critics."""
    critic_mock = _mock_mini(_hop("critic", 0.85))
    agent = TACOAgent(minis={
        "brain":   _mock_mini(_hop("brain", 0.70)),
        "harness": _mock_mini(_hop("harness", 0.80)),
        "critic":  critic_mock,
    })
    chain = agent.run("what are the risks?", force_critic=True)
    critic_mock.run.assert_called_once()
    assert chain.routed_to_critics is True
    assert chain.hops[-1].hop_type == "critic"


def test_critic_no_arch_returns_zero_confidence():
    """Critic with no arch_name degrades cleanly."""
    critic = TACOminiCritic()
    hop = critic.run(TACOContext(query="test", arch_name=None))
    assert hop.confidence == 0.0
    assert hop.hop_type == "critic"
    assert hop.metadata.get("had_moe") is False


def test_critic_missing_moe_file(tmp_path):
    """Critic returns had_moe=False when report dir has no MoE file."""
    critic = TACOminiCritic(report_dir=tmp_path)
    arch_dir = tmp_path / "my_arch"
    arch_dir.mkdir()
    hop = critic.run(TACOContext(query="test", arch_name="my_arch"))
    assert hop.confidence == 0.0
    assert hop.metadata["reason"] == "no_moe_file"


def test_critic_reads_moe_file(tmp_path):
    """Critic extracts confidence and signals from 07_moe_orchestrator.json."""
    import json as _json
    arch_dir = tmp_path / "my_arch"
    arch_dir.mkdir()
    moe_data = {
        "confidence": {
            "final": 72.0,
            "interpretation": "SOLID",
        },
        "expert_validations": {
            "architect": {"validation_status": "APPROVED"},
            "red_team":  {"validation_status": "NEEDS_REVISION"},
        },
        "scrum_master": {
            "final_confidence": 68.0,
            "redesign_signal": False,
        },
    }
    (arch_dir / "07_moe_orchestrator.json").write_text(_json.dumps(moe_data))
    critic = TACOminiCritic(report_dir=tmp_path)
    hop = critic.run(TACOContext(query="test", arch_name="my_arch"))
    assert hop.hop_type == "critic"
    assert hop.metadata["had_moe"] is True
    assert abs(hop.confidence - 0.72) < 0.001
    assert hop.metadata["redesign_signal"] is False
    assert hop.metadata["critics_count"] == 2
    assert "MoE conf=0.72" in hop.response_summary
