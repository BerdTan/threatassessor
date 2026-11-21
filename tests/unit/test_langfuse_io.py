"""Langfuse spans must be real roots with input/output (Entry 264 step 6c).

Langfuse support: sessions showed no messages because spans had only metadata,
lasted 0 ms, and pointed at a parent Langfuse never received.
"""
from unittest.mock import MagicMock

from chatbot.harness.event_broker import HarnessEvent
from chatbot.harness.sinks import LangfuseSink


def _sink():
    s = LangfuseSink.__new__(LangfuseSink)
    s._lf, s._trace = MagicMock(), None
    s._should_handle = lambda e: True
    s._routing_mode = ""
    return s


def test_mcp_span_is_root_with_input_output_and_duration():
    s = _sink()
    span = MagicMock()
    span._otel_span.start_time = 1_000_000_000
    s._lf.start_observation.return_value = span
    s.emit(HarnessEvent("mcp_tool_call", "analyze_architecture", "r", "t", {
        "tool": "analyze_architecture", "input": {"mmd_content": "graph TD"},
        "output": "{}", "duration_s": 2.5, "session_id": "sess-1", "caller_id": "c"}))
    kw = s._lf.start_observation.call_args.kwargs
    assert "trace_context" not in kw  # no synthetic parent
    assert kw["input"] == {"mmd_content": "graph TD"} and kw["as_type"] == "tool"
    span.update.assert_called_once_with(output="{}")
    span.end.assert_called_once_with(end_time=1_000_000_000 + 2_500_000_000)


def test_run_trace_is_root_with_input_and_scores_use_real_trace_id():
    s = _sink()
    tr = MagicMock()
    tr.trace_id = "f" * 32
    s._lf.start_observation.return_value = tr
    s.emit(HarnessEvent("run_start", "harness", "run-xyz", "t",
                        {"architecture": "arch", "scenario": "api_only", "session_id": "s", "caller_id": "c"}))
    kw = s._lf.start_observation.call_args.kwargs
    assert "trace_context" not in kw and kw["input"]["architecture"] == "arch"
    assert kw["metadata"]["run_id"] == "run-xyz"
    s.emit(HarnessEvent("aivss_complete", "harness", "run-xyz", "t",
                        {"inbound": 1, "internal": 1, "outbound": 1}))
    ids = {c.kwargs["trace_id"] for c in s._lf.create_score.call_args_list}
    assert ids == {"f" * 32}


def test_logger_event_carries_input_output_duration(monkeypatch):
    from mcp_server.access_logger import MCPAccessLogger
    lg = MCPAccessLogger()
    sent = []
    monkeypatch.setattr(lg, "_emit_event", lambda *a, **k: sent.append((a, k)))
    lg.begin_call("analyze_architecture", {"mmd_content": "graph TD"})
    lg.record_tool_call("analyze_architecture")  # inside a call: deferred
    assert sent == []
    lg.end_call('{"ok": 1}')
    (a, k), = sent
    assert k["io"]["input"] == "{'mmd_content': 'graph TD'}" and k["io"]["output"] == '{"ok": 1}'
    assert k["io"]["duration_s"] >= 0


def test_logger_clips_large_io(monkeypatch):
    from mcp_server.access_logger import MCPAccessLogger, _IO_MAX
    lg = MCPAccessLogger()
    sent = []
    monkeypatch.setattr(lg, "_emit_event", lambda *a, **k: sent.append(k))
    lg.begin_call("t", {"x": "a" * 10_000})
    lg.end_call("b" * 10_000)
    assert len(sent[0]["io"]["input"]) < _IO_MAX + 60 and "clipped" in sent[0]["io"]["output"]


def test_real_sdk_root_span_has_no_parent_and_carries_io():
    from langfuse import Langfuse
    lf = Langfuse(public_key="pk-x", secret_key="sk-x", host="http://127.0.0.1:9")
    sp = lf.start_observation(name="mcp:x", as_type="tool", input={"a": 1})
    assert sp._otel_span.parent is None
