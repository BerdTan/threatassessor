"""
Unit tests — JevTATBLabeller (Engine Item 17).

All tests are offline: Jev API calls are mocked. No network, no LLM.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from chatbot.modules.ta_brain_jev_labeller import (
    JevTATBLabeller,
    _build_state,
    run_jev_validation,
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _instance(arch_id="01_minimal_vulnerable", arch_type="generic", techniques=None,
              controls_missing=None, aivss=5.0, nodes=4, edges=3):
    return {
        "arch_id": arch_id,
        "arch_type": arch_type,
        "node_count": nodes,
        "edge_count": edges,
        "techniques": techniques if techniques is not None else ["T1059", "T1078", "T1190"],
        "controls_missing": controls_missing if controls_missing is not None else ["MFA", "WAF"],
        "aivss_composite": aivss,
        "aivss_severity": "HIGH" if aivss >= 7 else "MEDIUM",
        "hub_nodes": ["database", "loadbalancer"],
        "topology_signature": "abc123",
    }


def _jev_answer(scores: dict) -> dict:
    return {"answers": {k: {"score": v} for k, v in scores.items()}}


# ── _build_state ──────────────────────────────────────────────────────────────

def test_build_state_fields():
    inst = _instance()
    state = _build_state(inst)
    assert state["arch_type"] == "generic"
    assert state["node_count"] == 4
    assert state["technique_count"] == 3
    assert state["controls_missing_count"] == 2
    assert state["hub_node_count"] == 2


def test_build_state_missing_keys():
    state = _build_state({})
    assert state["arch_type"] == "unknown"
    assert state["technique_count"] == 0


# ── JevTATBLabeller.label ──────────────────────────────────────────────────────

def test_label_returns_four_dims_plus_composite():
    labeller = JevTATBLabeller(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = _jev_answer({
        "threat_relevant": 0.9,
        "ttp_accurate": 0.8,
        "risk_defensible": 0.7,
        "plan_actionable": 0.85,
    })
    with patch("requests.post", return_value=mock_resp):
        result = labeller.label(_instance())
    assert result["threat_relevant"] == 0.9
    assert result["ttp_accurate"] == 0.8
    assert result["risk_defensible"] == 0.7
    assert result["plan_actionable"] == 0.85
    assert result["composite"] == pytest.approx((0.9 + 0.8 + 0.7 + 0.85) / 4, abs=1e-4)
    assert "error" not in result


def test_label_fallback_on_api_error():
    labeller = JevTATBLabeller(api_key="test-key")
    with patch("requests.post", side_effect=ConnectionError("timeout")):
        result = labeller.label(_instance())
    for dim in ("threat_relevant", "ttp_accurate", "risk_defensible", "plan_actionable"):
        assert result[dim] == 0.5
    assert result["composite"] == 0.5
    assert "error" in result


def test_label_missing_answer_key_falls_back_to_half():
    labeller = JevTATBLabeller(api_key="test-key")
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"answers": {"threat_relevant": {"score": 0.9}}}
    with patch("requests.post", return_value=mock_resp):
        result = labeller.label(_instance())
    assert result["threat_relevant"] == 0.9
    assert result["ttp_accurate"] == 0.5   # missing → neutral


# ── JevTATBLabeller.brier_on_corpus ───────────────────────────────────────────

def test_brier_on_corpus_promote_when_jev_beats_baseline(tmp_path):
    """Jev ttp_accurate=1.0, brain recall=1.0 → brier=0.0 < baseline=0.25."""
    labeller = JevTATBLabeller(api_key="test-key")
    inst = _instance(techniques=["T1059", "T1078", "T1190"])
    brain_path = tmp_path / "ta_brain.json"
    brain_path.write_text("{}")

    jev_scores = {"threat_relevant": 1.0, "ttp_accurate": 1.0,
                  "risk_defensible": 1.0, "plan_actionable": 1.0, "composite": 1.0}
    brain_result = {"predictions": {"techniques": ["T1059", "T1078", "T1190"]}}  # recall = 1.0

    with patch.object(labeller, "label", return_value=jev_scores), \
         patch("chatbot.modules.ta_brain_jev_labeller.query_brain", return_value=brain_result):
        result = labeller.brier_on_corpus([inst], brain_path)

    assert result["n_instances"] == 1
    assert result["avg_brier"] == pytest.approx(0.0, abs=1e-6)
    assert result["promote"] is True
    assert result["improvement"] > 0


def test_brier_on_corpus_no_promote_when_jev_same_as_baseline(tmp_path):
    """Jev ttp_accurate=0.5, brain recall=1.0 → same as baseline → no improvement."""
    labeller = JevTATBLabeller(api_key="test-key")
    inst = _instance(techniques=["T1059"])
    brain_path = tmp_path / "ta_brain.json"
    brain_path.write_text("{}")

    jev_scores = {"threat_relevant": 0.5, "ttp_accurate": 0.5,
                  "risk_defensible": 0.5, "plan_actionable": 0.5, "composite": 0.5}
    brain_result = {"predictions": {"techniques": ["T1059"]}}  # recall = 1.0

    with patch.object(labeller, "label", return_value=jev_scores), \
         patch("chatbot.modules.ta_brain_jev_labeller.query_brain", return_value=brain_result):
        result = labeller.brier_on_corpus([inst], brain_path)

    assert result["improvement"] == pytest.approx(0.0, abs=1e-6)
    assert result["promote"] is False


def test_brier_on_corpus_skips_instances_without_techniques(tmp_path):
    labeller = JevTATBLabeller(api_key="test-key")
    brain_path = tmp_path / "ta_brain.json"
    brain_path.write_text("{}")
    empty = _instance(techniques=[])

    with patch.object(labeller, "label") as mock_label, \
         patch("chatbot.modules.ta_brain_jev_labeller.query_brain", return_value={"predictions": {"techniques": []}}):
        result = labeller.brier_on_corpus([empty], brain_path)

    mock_label.assert_not_called()
    assert "error" in result


# ── run_jev_validation ────────────────────────────────────────────────────────

def test_run_jev_validation_missing_instances(tmp_path):
    result = run_jev_validation(
        instances_path=tmp_path / "missing.jsonl",
        brain_path=tmp_path / "brain.json",
        hold_out_archs=frozenset({"01_minimal_vulnerable"}),
    )
    assert "error" in result


def test_run_jev_validation_filters_to_hold_out(tmp_path):
    instances_path = tmp_path / "instances.jsonl"
    brain_path = tmp_path / "ta_brain.json"
    brain_path.write_text("{}")

    hold_out_id = "01_minimal_vulnerable"
    train_id = "03_aws_3tier"
    instances = [
        _instance(arch_id=hold_out_id, techniques=["T1059"]),
        _instance(arch_id=train_id, techniques=["T1078"]),
    ]
    with instances_path.open("w") as fh:
        for inst in instances:
            fh.write(json.dumps(inst) + "\n")

    brain_result = {"predictions": {"techniques": ["T1059"]}}

    jev_scores = {"threat_relevant": 0.8, "ttp_accurate": 0.8,
                  "risk_defensible": 0.8, "plan_actionable": 0.8, "composite": 0.8}

    with patch.object(JevTATBLabeller, "label", return_value=jev_scores), \
         patch("chatbot.modules.ta_brain_jev_labeller.query_brain", return_value=brain_result):
        result = run_jev_validation(
            instances_path=instances_path,
            brain_path=brain_path,
            hold_out_archs=frozenset({hold_out_id}),
        )

    # Only hold-out instance scored — train instance excluded
    assert result["n_instances"] == 1
    assert result["per_instance"][0]["arch_id"] == hold_out_id
