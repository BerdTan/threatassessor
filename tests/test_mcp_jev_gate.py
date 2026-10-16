"""
Tests for _mcp_jev_gate — per-action Jev noul gate in mcp_server/server.py.

The mcp package is not installed in the test environment, so server.py is
imported with a lightweight stub for mcp.server.fastmcp.
"""
import sys
import types
import os
import pytest
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Bootstrap: stub the mcp package so server.py can be imported
# ---------------------------------------------------------------------------

def _stub_mcp():
    if "mcp" in sys.modules and hasattr(sys.modules["mcp"], "_stubbed"):
        return  # already done

    mcp_stub = types.ModuleType("mcp")
    mcp_stub._stubbed = True
    server_stub = types.ModuleType("mcp.server")
    fastmcp_stub = types.ModuleType("mcp.server.fastmcp")

    class FakeFastMCP:
        def __init__(self, **k):
            pass
        def tool(self):
            return lambda f: f

    fastmcp_stub.FastMCP = FakeFastMCP
    sys.modules["mcp"] = mcp_stub
    sys.modules["mcp.server"] = server_stub
    sys.modules["mcp.server.fastmcp"] = fastmcp_stub

    # stub mcp_server sub-modules to avoid circular import noise
    jc = types.ModuleType("mcp_server.job_client")
    al_mod = types.ModuleType("mcp_server.access_logger")

    class FakeLog:
        def record_tool_call(self, *a, **k):
            pass

    al_mod.get_access_logger = lambda: FakeLog()
    sys.modules["mcp_server.job_client"] = jc
    sys.modules["mcp_server.access_logger"] = al_mod


_stub_mcp()

from mcp_server import server  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_jev_circuit():
    """Ensure JevClient circuit breaker is reset before each test."""
    try:
        from chatbot.modules.jev_client import JevClient
        JevClient.reset_circuit()
    except Exception:
        pass
    yield


# ---------------------------------------------------------------------------
# _HIGH_RISK_TOOLS coverage
# ---------------------------------------------------------------------------

def test_high_risk_tools_contains_expected():
    expected = {
        "analyze_architecture", "run_expert_review", "export_assessment",
        "record_brain_feedback", "generate_synthetic_architectures", "run_taclaw",
    }
    assert expected == server._HIGH_RISK_TOOLS


def test_high_risk_tools_excludes_read_tier():
    read_tools = {"list_architectures", "get_threat_briefing", "get_tatb_scores",
                  "lookup_mitre_technique", "query_ta_brain", "get_ciso_brief"}
    assert not (read_tools & server._HIGH_RISK_TOOLS)


def test_threshold_is_conservative():
    assert server._JEV_GATE_THRESHOLD <= 0.15


# ---------------------------------------------------------------------------
# Gate: fail-open behaviour
# ---------------------------------------------------------------------------

def test_gate_allows_when_jev_disabled():
    with patch.dict(os.environ, {"JEV_ENABLED": "0"}):
        result = server._mcp_jev_gate("analyze_architecture", "test_arch", "ssp=low")
    assert result is None


def test_gate_allows_when_no_api_key():
    env = {k: v for k, v in os.environ.items() if k != "JEV_API_KEY"}
    env.pop("JEV_API_KEY", None)
    with patch.dict(os.environ, env, clear=True):
        result = server._mcp_jev_gate("run_taclaw", "my_repo", "type=directory")
    assert result is None


def test_gate_allows_read_tier_tools():
    result = server._mcp_jev_gate("list_architectures", "", "")
    assert result is None


def test_gate_allows_when_jev_returns_empty():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {}   # empty → default 1.0 → allow
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        result = server._mcp_jev_gate("analyze_architecture", "arch", "ctx")
    assert result is None


def test_gate_allows_when_jev_raises():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.side_effect = RuntimeError("network error")
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        result = server._mcp_jev_gate("export_assessment", "arch", "save=True")
    assert result is None


# ---------------------------------------------------------------------------
# Gate: deny behaviour
# ---------------------------------------------------------------------------

def test_gate_denies_when_noul_below_threshold():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {"invocation_authorized": {"noul": 0.05}}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        result = server._mcp_jev_gate("run_expert_review", "arch", "mode=parallel")
    assert result is not None
    assert "authorization gate" in result
    assert "run_expert_review" in result
    assert "0.05" in result or "0.050" in result


def test_gate_allows_when_noul_at_threshold():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {"invocation_authorized": {"noul": server._JEV_GATE_THRESHOLD}}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        result = server._mcp_jev_gate("run_taclaw", "arch", "ctx")
    assert result is None  # < threshold → deny; == threshold → allow


def test_gate_denies_all_high_risk_tools_on_low_noul():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {"invocation_authorized": {"noul": 0.01}}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        for tool in server._HIGH_RISK_TOOLS:
            result = server._mcp_jev_gate(tool, "arch", "ctx")
            assert result is not None, f"Expected deny for {tool}"


# ---------------------------------------------------------------------------
# Gate: state payload reaches Jev
# ---------------------------------------------------------------------------

def test_gate_passes_tool_name_in_state():
    mock_jev = MagicMock()
    mock_jev.is_enabled.return_value = True
    mock_jev.ask.return_value = {}
    with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
        server._mcp_jev_gate("export_assessment", "my_arch", "save=True")
    call_kwargs = mock_jev.ask.call_args
    state = call_kwargs[1]["state"] if call_kwargs[1] else call_kwargs[0][0]
    assert state["tool_name"] == "export_assessment"
    assert state["arch_name"] == "my_arch"
