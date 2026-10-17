"""
Unit tests for Jev Phase 2 integration points.

❻  _jev_filter_ap_techniques  — ground_truth_generator.py
❽  _build_posture_signal       — ta_exporter.py

All offline. No network calls.
"""
import os
from unittest.mock import MagicMock, patch

import pytest

from chatbot.modules.ground_truth_generator import _jev_filter_ap_techniques
from chatbot.modules.ta_exporter import _build_posture_signal


@pytest.fixture(autouse=True)
def reset_circuit():
    try:
        from chatbot.modules.jev_client import JevClient
        JevClient.reset_circuit()
    except Exception:
        pass
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ap(techs=("T1078", "T1190", "T1059"), path=("n1", "n2", "n3")):
    per_node = {
        "n1": ["T1078"],
        "n2": ["T1190"],
        "n3": ["T1059"],
    }
    return {
        "path": list(path),
        "techniques": list(techs),
        "per_node_techniques": per_node,
        "technique_context": {},
    }


def _make_nodes():
    return {
        "n1": {"label": "Internet Gateway"},
        "n2": {"label": "Web Server"},
        "n3": {"label": "Database"},
    }


def _make_gt(arch_type="cloud", attack_paths=2, critical=1):
    aps = [
        {"criticality_tier": "critical" if i < critical else "medium"}
        for i in range(attack_paths)
    ]
    return {
        "techniques": ["T1078", "T1190"],
        "attack_paths": aps,
        "metadata": {"architecture_type": arch_type},
    }


def _make_gov(risk_level="HIGH", composite=8.5):
    return {
        "overall_risk_level": risk_level,
        "aivss": {"overall": {"composite": composite}},
    }


# ---------------------------------------------------------------------------
# ❻ _jev_filter_ap_techniques — fail-open behaviour
# ---------------------------------------------------------------------------

def test_filter_does_nothing_when_jev_disabled():
    with patch.dict(os.environ, {"JEV_ENABLED": "0"}):
        ap = _make_ap()
        original_techs = list(ap["techniques"])
        _jev_filter_ap_techniques(ap, _make_nodes(), "cloud")
    assert ap["techniques"] == original_techs


def test_filter_does_nothing_when_no_api_key():
    env = {k: v for k, v in os.environ.items() if k != "JEV_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        ap = _make_ap()
        original_techs = list(ap["techniques"])
        _jev_filter_ap_techniques(ap, _make_nodes(), "cloud")
    assert ap["techniques"] == original_techs


def test_filter_fails_open_on_exception():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.side_effect = RuntimeError("network down")
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        ap = _make_ap()
        original_techs = list(ap["techniques"])
        _jev_filter_ap_techniques(ap, _make_nodes(), "cloud")
    assert ap["techniques"] == original_techs


def test_filter_no_change_when_jev_returns_empty():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        ap = _make_ap()
        original_techs = list(ap["techniques"])
        _jev_filter_ap_techniques(ap, _make_nodes(), "cloud")
    assert ap["techniques"] == original_techs


# ---------------------------------------------------------------------------
# ❻ _jev_filter_ap_techniques — filter behaviour
# ---------------------------------------------------------------------------

def test_filter_removes_low_noul_techniques():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {
        "T1078": {"noul": 0.90},
        "T1190": {"noul": 0.10},   # below 0.25 threshold — should be dropped
        "T1059": {"noul": 0.85},
    }
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        ap = _make_ap()
        _jev_filter_ap_techniques(ap, _make_nodes(), "cloud")
    assert "T1190" not in ap["techniques"]
    assert "T1078" in ap["techniques"]
    assert "T1059" in ap["techniques"]


def test_filter_records_dropped_in_technique_context():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {
        "T1078": {"noul": 0.10},
        "T1190": {"noul": 0.05},
        "T1059": {"noul": 0.80},
    }
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        ap = _make_ap()
        _jev_filter_ap_techniques(ap, _make_nodes(), "cloud")
    ctx = ap["technique_context"]
    assert ctx["jev_filtered_count"] == 2
    assert "T1078" in ctx["jev_filtered"]
    assert "T1190" in ctx["jev_filtered"]


def test_filter_keeps_all_when_all_above_threshold():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {
        "T1078": {"noul": 0.80},
        "T1190": {"noul": 0.70},
        "T1059": {"noul": 0.90},
    }
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        ap = _make_ap()
        original_count = len(ap["techniques"])
        _jev_filter_ap_techniques(ap, _make_nodes(), "cloud")
    assert len(ap["techniques"]) == original_count
    assert "jev_filtered_count" not in ap["technique_context"]


def test_filter_at_threshold_boundary_keeps_technique():
    from chatbot.modules.ground_truth_generator import _JEV_APPLICABILITY_THRESHOLD
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {
        "T1078": {"noul": _JEV_APPLICABILITY_THRESHOLD},  # exactly at threshold — keep
        "T1190": {"noul": 0.90},
        "T1059": {"noul": 0.90},
    }
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        ap = _make_ap()
        _jev_filter_ap_techniques(ap, _make_nodes(), "cloud")
    assert "T1078" in ap["techniques"]


def test_filter_passes_arch_type_and_path_labels_to_jev():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        ap = _make_ap()
        _jev_filter_ap_techniques(ap, _make_nodes(), "ai_system")
    call_kwargs = mock_jev.ask.call_args[1]
    assert call_kwargs["state"]["arch_type"] == "ai_system"
    assert "Internet Gateway" in call_kwargs["state"]["path"]


# ---------------------------------------------------------------------------
# ❽ _build_posture_signal — fail-open behaviour
# ---------------------------------------------------------------------------

def test_posture_signal_returns_none_when_jev_disabled():
    with patch.dict(os.environ, {"JEV_ENABLED": "0"}):
        result = _build_posture_signal(_make_gt(), _make_gov())
    assert result is None


def test_posture_signal_returns_none_when_no_api_key():
    env = {k: v for k, v in os.environ.items() if k != "JEV_API_KEY"}
    with patch.dict(os.environ, env, clear=True):
        result = _build_posture_signal(_make_gt(), _make_gov())
    assert result is None


def test_posture_signal_returns_none_on_exception():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.side_effect = RuntimeError("network down")
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        result = _build_posture_signal(_make_gt(), _make_gov())
    assert result is None


def test_posture_signal_returns_none_when_jev_returns_empty():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        result = _build_posture_signal(_make_gt(), _make_gov())
    assert result is None


# ---------------------------------------------------------------------------
# ❽ _build_posture_signal — signal shape and logic
# ---------------------------------------------------------------------------

def test_posture_signal_consistent_when_noul_high():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {"posture_consistent": {"noul": 0.82}}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        result = _build_posture_signal(_make_gt(), _make_gov())
    assert result is not None
    assert result["consistent"] is True
    assert result["noul"] == 0.82
    assert "ts" in result


def test_posture_signal_inconsistent_when_noul_low():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {"posture_consistent": {"noul": 0.30}}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        result = _build_posture_signal(_make_gt(), _make_gov())
    assert result["consistent"] is False
    assert result["noul"] == 0.30


def test_posture_signal_boundary_at_050():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {"posture_consistent": {"noul": 0.50}}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        result = _build_posture_signal(_make_gt(), _make_gov())
    assert result["consistent"] is True


def test_posture_signal_passes_arch_type_and_risk_to_jev():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        _build_posture_signal(_make_gt(arch_type="ai_system"), _make_gov(risk_level="CRITICAL"))
    call_kwargs = mock_jev.ask.call_args[1]
    state = call_kwargs["state"]
    assert state["arch_type"] == "ai_system"
    assert state["risk_level"] == "CRITICAL"


def test_posture_signal_present_in_export_bundle():
    from chatbot.modules.ta_exporter import build_export
    import tempfile, json
    from pathlib import Path

    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp)
        (p / "ground_truth.json").write_text(json.dumps({
            "techniques": ["T1078"],
            "attack_paths": [],
            "metadata": {"architecture_type": "cloud"},
        }))
        (p / "governance_signals.json").write_text(json.dumps({
            "overall_risk_level": "LOW",
            "aivss": {"overall": {"composite": 3.0}},
        }))
        for fname in ("07_moe_orchestrator.json", "ocsf_findings.json"):
            (p / fname).write_text("[]" if "ocsf" in fname else "{}")

        mock_jev = MagicMock()
        mock_jev.is_enabled.return_value = True
        mock_jev.ask.return_value = {"posture_consistent": {"noul": 0.75}}
        with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
            bundle = build_export("test_arch", p)

    assert "posture_signal" in bundle
    assert bundle["posture_signal"]["noul"] == 0.75
    assert bundle["posture_signal"]["consistent"] is True
