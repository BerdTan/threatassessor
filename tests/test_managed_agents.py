"""
Tests for the TA managed agent fleet.

Covers:
  - ManagedAgent base: tool loop, tool dispatch, output parsing, max_iterations guard
  - ManagedAgentRegistry: register, get, list
  - TAclawInvestigationAgent: should_run gates, tool handlers, context injection
  - llm_client.ChatResponse: dataclass fields
"""

import json
import unittest
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

# ── ChatResponse ──────────────────────────────────────────────────────────────

class TestChatResponse(unittest.TestCase):
    def test_fields(self):
        from agentic.llm_client import ChatResponse
        r = ChatResponse(content="hello", tool_calls=[], stop_reason="end_turn", tokens_used=10, model="x")
        self.assertEqual(r.content, "hello")
        self.assertEqual(r.stop_reason, "end_turn")
        self.assertEqual(r.tool_calls, [])

    def test_tool_calls_present(self):
        from agentic.llm_client import ChatResponse
        tc = [{"id": "tc_1", "name": "get_block_signals", "input": {"job_id": "j1"}}]
        r = ChatResponse(content=None, tool_calls=tc, stop_reason="tool_use", tokens_used=50, model="x")
        self.assertEqual(r.stop_reason, "tool_use")
        self.assertEqual(len(r.tool_calls), 1)
        self.assertEqual(r.tool_calls[0]["name"], "get_block_signals")


# ── ManagedAgent base ─────────────────────────────────────────────────────────

class _EchoAgent:
    """Minimal concrete ManagedAgent for testing the base loop."""

    from chatbot.agents.managed.base import ManagedAgent, AgentTool, ManagedAgentResult  # type: ignore

    pass  # loaded below to avoid import at class-definition time


def _make_echo_agent():
    from chatbot.agents.managed.base import ManagedAgent, AgentTool

    class EchoAgent(ManagedAgent):
        agent_id = "echo_test"
        description = "Test echo agent"
        system_prompt = "You are a test agent."

        def _register_tools(self):
            self._add_tool(AgentTool(
                name="echo",
                description="Echo input back",
                input_schema={"type": "object", "properties": {"msg": {"type": "string"}}, "required": ["msg"]},
                handler=lambda inp: json.dumps({"echoed": inp.get("msg", "")}),
            ))

        def build_task(self, context):
            return f"Echo: {context.get('msg', '')}"

    return EchoAgent()


class TestManagedAgentBase(unittest.TestCase):
    def _mock_chat_end_turn(self, content):
        from agentic.llm_client import ChatResponse
        mock = MagicMock()
        mock.chat.return_value = ChatResponse(
            content=content,
            tool_calls=[],
            stop_reason="end_turn",
            tokens_used=20,
            model="test",
        )
        return mock

    def _mock_chat_tool_then_end(self, tool_name, tool_input, final_content):
        from agentic.llm_client import ChatResponse
        call_count = [0]

        def _chat(**kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return ChatResponse(
                    content=None,
                    tool_calls=[{"id": "tc_1", "name": tool_name, "input": tool_input}],
                    stop_reason="tool_use",
                    tokens_used=30,
                    model="test",
                )
            return ChatResponse(
                content=final_content,
                tool_calls=[],
                stop_reason="end_turn",
                tokens_used=20,
                model="test",
            )

        mock = MagicMock()
        mock.chat.side_effect = lambda **kw: _chat(**kw)
        return mock

    def test_end_turn_immediately(self):
        agent = _make_echo_agent()
        mock_client = self._mock_chat_end_turn('{"result": "done"}')
        with patch("agentic.llm_client.LLMClient", return_value=mock_client):
            result = agent.run({"msg": "hello"})
        self.assertTrue(result.success)
        self.assertEqual(result.tool_calls_made, 0)
        self.assertEqual(result.output.get("result"), "done")

    def test_tool_call_then_end(self):
        agent = _make_echo_agent()
        mock_client = self._mock_chat_tool_then_end(
            tool_name="echo",
            tool_input={"msg": "hi"},
            final_content='{"summary": "echoed hi"}',
        )
        with patch("agentic.llm_client.LLMClient", return_value=mock_client):
            result = agent.run({"msg": "hi"})
        self.assertTrue(result.success)
        self.assertEqual(result.tool_calls_made, 1)

    def test_unknown_tool_returns_error_json(self):
        agent = _make_echo_agent()
        result = agent._execute_tool("nonexistent", {})
        data = json.loads(result)
        self.assertIn("error", data)

    def test_max_iterations_guard(self):
        from agentic.llm_client import ChatResponse
        agent = _make_echo_agent()
        agent.max_iterations = 3

        mock = MagicMock()
        mock.chat.return_value = ChatResponse(
            content=None,
            tool_calls=[{"id": "tc_x", "name": "echo", "input": {"msg": "loop"}}],
            stop_reason="tool_use",
            tokens_used=10,
            model="test",
        )
        with patch("agentic.llm_client.LLMClient", return_value=mock):
            result = agent.run({})
        self.assertFalse(result.success)
        self.assertIn("max_iterations", result.output.get("error", ""))

    def test_should_run_default_true(self):
        agent = _make_echo_agent()
        ok, reason = agent.should_run({})
        self.assertTrue(ok)

    def test_skip_reason_propagated(self):
        from chatbot.agents.managed.base import ManagedAgent, AgentTool

        class SkipAgent(ManagedAgent):
            agent_id = "skip_test"
            description = ""
            system_prompt = ""
            def _register_tools(self): pass
            def build_task(self, ctx): return ""
            def should_run(self, ctx): return False, "test_skip"

        agent = SkipAgent()
        result = agent.run({})
        self.assertFalse(result.success)
        self.assertEqual(result.skip_reason, "test_skip")

    def test_llm_error_returns_failure(self):
        from agentic.llm_client import ChatResponse
        agent = _make_echo_agent()
        mock = MagicMock()
        mock.chat.return_value = ChatResponse(
            content=None, tool_calls=[], stop_reason="error", tokens_used=0, model="test"
        )
        with patch("agentic.llm_client.LLMClient", return_value=mock):
            result = agent.run({})
        self.assertFalse(result.success)

    def test_output_parse_json_in_markdown(self):
        agent = _make_echo_agent()
        md = '```json\n{"key": "value"}\n```'
        out = agent._parse_output(md)
        self.assertEqual(out.get("key"), "value")

    def test_output_parse_fallback_to_summary(self):
        agent = _make_echo_agent()
        out = agent._parse_output("plain text no json")
        self.assertIn("summary", out)

    def test_tokens_accumulated(self):
        from agentic.llm_client import ChatResponse
        agent = _make_echo_agent()
        call_count = [0]

        def _chat(**kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return ChatResponse(content=None, tool_calls=[{"id":"t","name":"echo","input":{"msg":"x"}}],
                                    stop_reason="tool_use", tokens_used=15, model="m")
            return ChatResponse(content='{}', tool_calls=[], stop_reason="end_turn", tokens_used=10, model="m")

        mock = MagicMock()
        mock.chat.side_effect = lambda **kw: _chat(**kw)
        with patch("agentic.llm_client.LLMClient", return_value=mock):
            result = agent.run({})
        self.assertEqual(result.tokens_used, 25)


# ── ManagedAgentRegistry ──────────────────────────────────────────────────────

class TestManagedAgentRegistry(unittest.TestCase):
    def _fresh_registry(self):
        from chatbot.agents.managed.registry import ManagedAgentRegistry
        return ManagedAgentRegistry()

    def test_register_and_get(self):
        reg = self._fresh_registry()
        agent = _make_echo_agent()
        reg.register(agent)
        self.assertIs(reg.get("echo_test"), agent)

    def test_get_unknown_returns_none(self):
        reg = self._fresh_registry()
        self.assertIsNone(reg.get("does_not_exist"))

    def test_list_agents(self):
        reg = self._fresh_registry()
        agent = _make_echo_agent()
        reg.register(agent)
        listing = reg.list_agents()
        ids = [a["agent_id"] for a in listing]
        self.assertIn("echo_test", ids)

    def test_get_registry_singleton_has_investigator(self):
        # get_registry() auto-registers TAclawInvestigationAgent
        import importlib
        import chatbot.agents.managed.registry as reg_mod
        # Reset singleton for isolation
        reg_mod._registry = None
        reg = reg_mod.get_registry()
        agent = reg.get("taclaw_investigator")
        self.assertIsNotNone(agent)
        self.assertEqual(agent.agent_id, "taclaw_investigator")


# ── TAclawInvestigationAgent ──────────────────────────────────────────────────

class TestTAclawInvestigationAgent(unittest.TestCase):
    def _agent(self):
        from chatbot.agents.managed.taclaw_investigator import TAclawInvestigationAgent
        return TAclawInvestigationAgent()

    def _block_context(self, **overrides):
        ctx = {
            "job_id": "j_test",
            "arch_name": "test_arch",
            "arch_type": "microservices",
            "gate": "BLOCK",
            "bouncer_reason": "exploitation.blocked=True",
            "fired_detect_rules": ["DETECT-INJ-001"],
            "max_severity": "Critical",
            "pipeline_result": {},
        }
        ctx.update(overrides)
        return ctx

    # should_run

    def test_should_run_pass_block(self):
        agent = self._agent()
        ok, _ = agent.should_run(self._block_context())
        self.assertTrue(ok)

    def test_should_run_skip_no_block(self):
        agent = self._agent()
        ok, reason = agent.should_run({"gate": "PASS"})
        self.assertFalse(ok)
        self.assertEqual(reason, "gate not BLOCK")

    def test_should_run_skip_kill_switch(self):
        agent = self._agent()
        ok, reason = agent.should_run(self._block_context(bouncer_reason="kill_switch"))
        self.assertFalse(ok)
        self.assertIn("kill_switch", reason)

    def test_should_run_skip_blocked_architectures(self):
        agent = self._agent()
        ok, reason = agent.should_run(self._block_context(bouncer_reason="blocked_architectures"))
        self.assertFalse(ok)
        self.assertIn("blocked_architectures", reason)

    def test_should_run_jev_disabled_passes(self):
        agent = self._agent()
        with patch("chatbot.modules.jev_client.get_jev_client", side_effect=ImportError):
            ok, _ = agent.should_run(self._block_context())
        self.assertTrue(ok)

    def test_should_run_jev_low_noul_skips(self):
        agent = self._agent()
        mock_jev = MagicMock()
        mock_jev.is_enabled.return_value = True
        mock_jev.noul.return_value = MagicMock(noul=0.10)
        with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
            ok, reason = agent.should_run(self._block_context())
        self.assertFalse(ok)
        self.assertIn("jev_gate", reason)

    def test_should_run_jev_sufficient_noul_passes(self):
        agent = self._agent()
        mock_jev = MagicMock()
        mock_jev.is_enabled.return_value = True
        mock_jev.noul.return_value = MagicMock(noul=0.75)
        with patch("chatbot.modules.jev_client.get_jev_client", return_value=mock_jev):
            ok, _ = agent.should_run(self._block_context())
        self.assertTrue(ok)

    # tool handlers

    def test_tool_get_block_signals_known_reason(self):
        agent = self._agent()
        agent._context = self._block_context()
        result = json.loads(agent._tool_get_block_signals({"job_id": "j_test"}))
        self.assertEqual(result["bouncer_check"], "exploitation.blocked=True")
        self.assertIn("injection", result["bouncer_label"].lower())
        self.assertIn("DETECT-INJ-001", result["detect_rules_fired"])

    def test_tool_get_block_signals_unknown_reason(self):
        agent = self._agent()
        agent._context = self._block_context(bouncer_reason="mystery_check")
        result = json.loads(agent._tool_get_block_signals({"job_id": "j_test"}))
        self.assertEqual(result["bouncer_check"], "mystery_check")
        self.assertIn("bouncer_remediation_hint", result)

    def test_tool_get_rule_detail_found(self):
        agent = self._agent()
        # Patch _load_rules to return a known rule
        fake_rules = {
            "DETECT-INJ-001": {
                "id": "DETECT-INJ-001",
                "name": "Test Injection",
                "domain": "INJ",
                "severity": "Critical",
                "description": "Injection test",
                "kill_chain_stage": "execution",
                "atlas_tactic": "AML.T0051",
                "owasp": ["A03"],
                "csa_art": ["ART-3.1"],
                "tuning_note": "Adjust threshold",
            }
        }
        with patch("chatbot.agents.managed.taclaw_investigator._load_rules", return_value=fake_rules):
            result = json.loads(agent._tool_get_rule_detail({"rule_id": "DETECT-INJ-001"}))
        self.assertEqual(result["id"], "DETECT-INJ-001")
        self.assertEqual(result["severity"], "Critical")

    def test_tool_get_rule_detail_not_found(self):
        agent = self._agent()
        with patch("chatbot.agents.managed.taclaw_investigator._load_rules", return_value={}):
            result = json.loads(agent._tool_get_rule_detail({"rule_id": "DETECT-ZZZ-999"}))
        self.assertIn("error", result)

    def test_tool_query_brain_patterns_no_match(self):
        agent = self._agent()
        with patch("chatbot.agents.managed.taclaw_investigator._load_brain", return_value={"patterns": []}):
            result = json.loads(agent._tool_query_brain_patterns({"arch_type": "anything"}))
        self.assertEqual(result["patterns_found"], 0)

    def test_tool_query_brain_patterns_match(self):
        agent = self._agent()
        brain = {"patterns": [
            {"id": "P1", "arch_types": ["microservices"], "frequency": 5,
             "top_techniques": ["T1190"], "top_components": ["api_gateway"]},
        ]}
        with patch("chatbot.agents.managed.taclaw_investigator._load_brain", return_value=brain):
            result = json.loads(agent._tool_query_brain_patterns({"arch_type": "microservices"}))
        self.assertEqual(result["patterns_found"], 1)
        self.assertEqual(result["patterns"][0]["id"], "P1")

    def test_tool_synthesize_stores_result(self):
        agent = self._agent()
        agent._synthesis_result = None
        inp = {
            "block_summary": "Injection detected",
            "root_signals": ["DETECT-INJ-001"],
            "brain_context": "No prior patterns",
            "remediation_steps": ["Sanitise input"],
            "confidence": "high",
        }
        raw = json.loads(agent._tool_synthesize_remediation(inp))
        self.assertEqual(raw["status"], "synthesis_complete")
        self.assertIsNotNone(agent._synthesis_result)
        self.assertEqual(agent._synthesis_result["confidence"], "high")

    def test_build_task_includes_arch_and_reason(self):
        agent = self._agent()
        ctx = self._block_context(arch_name="my_arch", bouncer_reason="exploitation.blocked=True")
        task = agent.build_task(ctx)
        self.assertIn("my_arch", task)
        self.assertIn("exploitation.blocked=True", task)

    # run integration (mocked LLM — full loop with synthesize call)

    def test_run_produces_investigation_report(self):
        from agentic.llm_client import ChatResponse
        agent = self._agent()
        ctx = self._block_context()

        synthesis_input = {
            "block_summary": "Injection in input",
            "root_signals": ["DETECT-INJ-001"],
            "brain_context": "No prior patterns",
            "remediation_steps": ["Sanitise input", "Add WAF rule"],
            "confidence": "high",
        }

        call_count = [0]

        def _mock_chat(**kw):
            call_count[0] += 1
            if call_count[0] == 1:
                # First: request get_block_signals
                return ChatResponse(
                    content=None,
                    tool_calls=[{"id": "t1", "name": "get_block_signals", "input": {"job_id": "j_test"}}],
                    stop_reason="tool_use", tokens_used=20, model="m",
                )
            if call_count[0] == 2:
                # Second: call synthesize
                return ChatResponse(
                    content=None,
                    tool_calls=[{"id": "t2", "name": "synthesize_remediation", "input": synthesis_input}],
                    stop_reason="tool_use", tokens_used=30, model="m",
                )
            # Third: end turn with synthesis JSON
            return ChatResponse(
                content=json.dumps({"status": "synthesis_complete"}),
                tool_calls=[], stop_reason="end_turn", tokens_used=10, model="m",
            )

        mock_client = MagicMock()
        mock_client.chat.side_effect = lambda **kw: _mock_chat(**kw)

        with patch("agentic.llm_client.LLMClient", return_value=mock_client):
            with patch("chatbot.agents.managed.taclaw_investigator._load_brain", return_value={"patterns": []}):
                result = agent.run(ctx)

        self.assertTrue(result.success)
        self.assertIn("block_summary", result.output)
        self.assertEqual(result.output["confidence"], "high")
        self.assertGreaterEqual(result.tool_calls_made, 2)

    def test_run_skips_when_gate_pass(self):
        agent = self._agent()
        result = agent.run({"gate": "PASS"})
        self.assertFalse(result.success)
        self.assertEqual(result.skip_reason, "gate not BLOCK")

    def test_agent_has_five_tools(self):
        agent = self._agent()
        tool_names = {t.name for t in agent.tools}
        self.assertEqual(tool_names, {
            "get_block_signals",
            "query_brain_patterns",
            "get_rule_detail",
            "get_pipeline_context",
            "synthesize_remediation",
        })


if __name__ == "__main__":
    unittest.main()
