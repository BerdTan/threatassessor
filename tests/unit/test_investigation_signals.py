"""Entry 264: caller attribution + per-run usage totals for incident replay."""
from chatbot.harness.caller_context import build_caller_context
from chatbot.harness.event_broker import EventBrokerCritic, HarnessEvent


def _gen(run_id, p, c, cost):
    return HarnessEvent("critic_generation", "red_team", run_id, "t",
                        {"prompt_tokens": p, "completion_tokens": c, "cost_usd": cost})


class TestCallerContext:
    def test_asserted_label_used(self):
        c = build_caller_context({"TM-CALLER": "ci-bot"}, "1.2.3.4", "rest")
        assert c["caller_id"] == "ci-bot" and c["caller_asserted"] is True and c["source"] == "rest"
        assert c["session_id"].startswith("ci-bot:") and c["session_asserted"] is False

    def test_header_case_insensitive(self):
        assert build_caller_context({"tm-caller": "x"})["caller_id"] == "x"

    def test_anonymous_is_stable_hash_not_raw_ip(self):
        a = build_caller_context({}, "10.0.0.9")
        b = build_caller_context({}, "10.0.0.9")
        assert a == b and not a["caller_asserted"]
        assert a["caller_id"].startswith("anon-") and "10.0.0.9" not in a["caller_id"]
        assert a["caller_id"] != build_caller_context({}, "10.0.0.8")["caller_id"]

    def test_label_sanitised_and_capped(self):
        c = build_caller_context({"TM-CALLER": "a b/../\n" + "z" * 200})
        import re
        assert re.fullmatch(r"[A-Za-z0-9._-]+", c["caller_id"])
        assert len(c["caller_id"]) <= 64

    def test_empty_label_falls_back_to_anon(self):
        assert build_caller_context({"TM-CALLER": "   "}, "h")["caller_asserted"] is False

    def test_unknown_source_normalised(self):
        assert build_caller_context({}, "h", "weird")["source"] == "unknown"


class TestUsageTotals:
    def test_sums_critic_generations_per_run(self):
        b = EventBrokerCritic.__new__(EventBrokerCritic)
        b._usage, b._sinks, b._enabled = {}, [], False
        b.emit(_gen("r1", 100, 50, 0.01))
        b.emit(_gen("r1", 10, 5, 0.002))
        b.emit(_gen("r2", 1, 1, 0.5))
        u = b.usage("r1")
        assert (u["tokens"], u["cost_usd"], u["llm_calls"]) == (165, 0.012, 2)
        assert b.usage("r2")["tokens"] == 2

    def test_critic_complete_not_double_counted(self):
        b = EventBrokerCritic.__new__(EventBrokerCritic)
        b._usage, b._sinks, b._enabled = {}, [], False
        b.emit(HarnessEvent("critic_complete", "x", "r", "t",
                            {"moe_total_tokens": 999, "moe_total_cost": 9.0}))
        assert b.usage("r")["tokens"] == 0

    def test_unknown_run_is_zero_and_names_what_is_counted(self):
        b = EventBrokerCritic.__new__(EventBrokerCritic)
        b._usage = {}
        u = b.usage("nope")
        assert u["tokens"] == 0 and u["counted"] == "critic_generation"


class TestMcpAttribution:
    def test_caller_recorded_and_env_default(self, monkeypatch):
        from mcp_server.access_logger import MCPAccessLogger
        monkeypatch.setenv("TA_MCP_CALLER", "claude-desktop")
        lg = MCPAccessLogger()
        lg._broker = type("B", (), {"_enabled": False})()   # no emit
        lg.record_tool_call("run_expert_review", arch_name="a")
        lg.record_tool_call("get_job_status", caller_id="other")
        callers = [c["caller"] for c in lg._calls]
        assert callers == ["claude-desktop", "other"]

    def test_emits_mcp_tool_call_event(self):
        from mcp_server.access_logger import MCPAccessLogger
        got = []
        class B:
            _enabled = True
            def emit(self, e): got.append(e)
            def flush(self): pass
        lg = MCPAccessLogger(); lg._broker = B()
        lg.record_tool_call("analyze_architecture", success=False, caller_id="x")
        e = got[0]
        assert e.event_type == "mcp_tool_call" and len(e.run_id) == 32 and int(e.run_id, 16) >= 0  # valid Langfuse trace id
        assert e.payload["caller_id"] == "x" and e.payload["success"] is False
        assert e.payload["source"] == "mcp"

    def test_broker_failure_never_breaks_tool_call(self):
        from mcp_server.access_logger import MCPAccessLogger
        class B:
            _enabled = True
            def emit(self, e): raise RuntimeError("boom")
            def flush(self): pass
        lg = MCPAccessLogger(); lg._broker = B()
        lg.record_tool_call("get_job_status")        # must not raise
        assert len(lg._calls) == 1

    def test_langfuse_preset_covers_mcp_event(self):
        from chatbot.harness.sinks import BaseSink
        class S(BaseSink):
            def emit(self, e): pass
        s = S({"events": ["mcp_trace"]})
        assert s._should_handle(HarnessEvent("mcp_tool_call", "t", "r", "ts", {}))
