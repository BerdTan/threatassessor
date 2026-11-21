"""Incident replays (Entry 264 step 5): each scenario asserts the response class
that fires AND that the trace names the caller, so an investigator can rebuild
the story. No LLM, no network.

Scenarios: relay, MCP worker, model probe, force_mode escalation.
"""
import logging

import pytest

from chatbot.harness import spend_gate as sg
from chatbot.harness.spend_ledger import LEDGER


@pytest.fixture
def client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from chatbot.api.app import create_app
    LEDGER.reset()
    p = tmp_path / "agent_governance.yaml"
    p.write_text("bouncer:\n  caller_limits: {window_s: 60, max_requests: 2}\n")
    monkeypatch.setenv("API_KEY", "k")
    monkeypatch.setattr(sg, "POLICY_PATH", p)
    yield TestClient(create_app())
    LEDGER.reset()


def _hit(c, caller):
    return c.post("/api/v1/boxing/run", json={},
                  headers={"TM-API-KEY": "k", "TM-CALLER": caller})


def test_relay_flood_is_throttled_and_traced(client, caplog):
    """A key resold to a relay: one label floods, gets 429, the trace names it."""
    caplog.set_level(logging.WARNING)
    codes = [_hit(client, "relay-7").status_code for _ in range(4)]
    assert codes[:2] != [429, 429] and codes[2] == 429 and codes[3] == 429
    assert any("throttle" in r.message and "caller=relay-7" in r.message for r in caplog.records)
    assert _hit(client, "honest-user").status_code != 429  # others unaffected


def test_mcp_workers_attributed_and_throttled_independently(client, monkeypatch):
    """MCP-as-worker: the MCP client sends its own label, so two workers do not
    share one anonymous bucket (before this fix every local MCP caller was one id)."""
    from mcp_server import job_client
    out = {}
    for name in ("worker-a", "worker-b"):
        monkeypatch.setenv("TA_MCP_CALLER", name)
        h = job_client._headers()
        assert h["TM-CALLER"] == name
        out[name] = h
    h = {"TM-API-KEY": "k"}
    for _ in range(3):
        r = client.post("/api/v1/boxing/run", json={}, headers={**h, "TM-CALLER": "worker-a"})
    assert r.status_code == 429
    assert client.post("/api/v1/boxing/run", json={}, headers={**h, "TM-CALLER": "worker-b"}).status_code != 429


def test_other_clients_send_a_caller_label(monkeypatch):
    from mcp_connector.client import MCPClient as TAClient
    from taclaw import cli
    monkeypatch.setenv("TA_CALLER", "ci-bot")
    assert TAClient(base_url="http://x", api_key="k")._headers()["TM-CALLER"] == "ci-bot"
    assert cli._headers({"api_key": "k"})["TM-CALLER"] == "ci-bot"


def test_model_probe_is_detected_but_response_is_alert_only():
    """Model probing: repeated queries of one arch raise probe_pattern, DETECT-ABU-001
    fires. The response class is alert-only: honest gap, recorded in the gap map."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts" / "tmeval"))
    import gap_map
    from chatbot.harness.rule_evaluator import RuleEvaluator
    from mcp_server.access_logger import MCPAccessLogger

    log = MCPAccessLogger()
    for _ in range(6):
        log.record_tool_call("analyze_architecture", arch_name="victim", caller_id="prober")
    sig = log.get_signals()
    assert sig["mcp_access"]["probe_pattern"] is True
    ids = [f["unmapped"]["rule_id"] for f in RuleEvaluator().evaluate(
        {"mcp_access": sig["mcp_access"]}, arch_name="victim", run_id="r")]
    assert "DETECT-ABU-001" in ids
    resp = {r["id"]: r["response"] for r in gap_map.build()["rows"]}
    assert resp["DETECT-ABU-001"] == "alert_only"  # flips when a response is added


def test_force_mode_escalation_costs_more_than_a_plain_request():
    """Was a strict xfail (gate was mode-blind); fixed in step 7."""
    assert sg.request_weight("analyze-stream", force_mode="full_moe") > \
           sg.request_weight("analyze-stream", force_mode=None)
    assert sg.request_weight("analyze-stream", force_mode="api_only") == 1


class TestSessionCorrelation:
    """Langfuse sessions: runs and tool calls of one client group under one session."""

    def test_header_wins_else_caller_day_bucket(self):
        from chatbot.harness.caller_context import build_caller_context as b
        a = b({"TM-CALLER": "c1", "TM-SESSION": "job-42"}, "h", today="2026-11-21")
        assert a["session_id"] == "job-42" and a["session_asserted"] is True
        d = b({"TM-CALLER": "c1"}, "h", today="2026-11-21")
        assert d["session_id"] == "c1:2026-11-21" and d["session_asserted"] is False

    def test_session_is_ascii_and_bounded(self):
        from chatbot.harness.caller_context import build_caller_context as b
        s = b({"TM-SESSION": "é" * 500 + "x"}, "h")["session_id"]
        assert s.isascii() and len(s) <= 64

    def test_clients_share_one_process_session(self, monkeypatch):
        monkeypatch.delenv("TA_SESSION", raising=False)
        from mcp_server import job_client
        from taclaw import cli
        a, b = job_client._headers()["TM-SESSION"], cli._headers({"api_key": "k"})["TM-SESSION"]
        assert a == b and a.startswith("sess-")

    def test_sink_scopes_spans_with_session_and_user(self, monkeypatch):
        """The Langfuse sink must wrap span creation in propagate_attributes."""
        import langfuse
        from chatbot.harness.event_broker import HarnessEvent
        from chatbot.harness.sinks import LangfuseSink
        seen = []

        class _Ctx:
            def __enter__(self): return self
            def __exit__(self, *a): return False

        monkeypatch.setattr(langfuse, "propagate_attributes", lambda **kw: (seen.append(kw), _Ctx())[1])
        sink = LangfuseSink.__new__(LangfuseSink)
        sink._lf, sink._trace = object(), None
        monkeypatch.setattr(sink, "_should_handle", lambda e: True, raising=False)
        monkeypatch.setattr(sink, "_emit", lambda e: None, raising=False)
        sink.emit(HarnessEvent("run_start", "harness", "r" * 32, "t",
                               {"session_id": "s-1", "caller_id": "u-1"}))
        sink.emit(HarnessEvent("critic_generation", "x", "r" * 32, "t", {}))  # later event keeps scope
        assert seen == [{"session_id": "s-1", "user_id": "u-1"}] * 2


def test_force_mode_reaches_the_generator_and_is_charged():
    """force_mode was a form field never passed on (NameError in the generator). It must
    reach analyze_with_progress, and a forced full_moe must charge the caller's ledger."""
    import inspect
    from chatbot.api.routes import streaming
    assert "force_mode" in inspect.signature(streaming.analyze_with_progress).parameters
    assert "force_mode=force_mode" in inspect.getsource(streaming.analyze_architecture_stream)
    assert "request_weight" in inspect.getsource(streaming.analyze_with_progress)
