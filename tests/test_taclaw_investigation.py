"""
Integration tests for the TAclaw investigation agent wire-in.

These tests verify that:
  A. The inv_context built from a BlockedPipelineError has the right shape
     for TAclawInvestigationAgent to consume.
  B. _run_taclaw_job produces result["investigation"] when gate=BLOCK,
     by running the full async function with mocked heavy dependencies.
  C. The investigation is skipped (not an error) for trivial blocks
     (kill_switch, blocked_architectures).
"""

from __future__ import annotations

import asyncio
import json
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# ── helpers ───────────────────────────────────────────────────────────────────

def _make_blocked_exc(reason: str = "exploitation.blocked=True",
                      detect_rules: list | None = None):
    """Construct a realistic BlockedPipelineError for testing."""
    from chatbot.harness.controller import BlockedPipelineError

    rules = detect_rules if detect_rules is not None else [
        {"rule_id": "DETECT-INJ-001", "severity": "Critical"}
    ]
    ctx = MagicMock()
    ctx.detect_summary = {
        "rules_fired": rules,
        "total_fired": len(rules),
    }
    exc = BlockedPipelineError(reason=reason, ctx=ctx)
    return exc


def _make_merged_graph(arch_type: str = "microservices"):
    """Minimal merged ArchitectureGraph mock."""
    merged = MagicMock()
    merged.nodes = [MagicMock(), MagicMock()]
    merged.edges = [MagicMock()]
    merged.adapter_metadata = {
        "source_formats": ["mmd"],
        "primary_arch_type": arch_type,
        "adapters_fidelity": [],
    }
    merged.source_trust = "unverified"
    return merged


def _make_synthesis_chat_responses():
    """Mock LLM chat responses: request get_block_signals → synthesize → end_turn."""
    from agentic.llm_client import ChatResponse

    call_count = [0]
    synthesis_input = {
        "block_summary": "Injection tag detected in architecture diagram",
        "root_signals": ["DETECT-INJ-001"],
        "brain_context": "No prior patterns found for this arch type",
        "remediation_steps": [
            "Remove <script> tag from architecture diagram",
            "Sanitise all node labels before submission",
        ],
        "confidence": "high",
    }

    def _chat(**kw):
        call_count[0] += 1
        if call_count[0] == 1:
            return ChatResponse(
                content=None,
                tool_calls=[{"id": "t1", "name": "get_block_signals", "input": {"job_id": "test_job"}}],
                stop_reason="tool_use", tokens_used=20, model="test",
            )
        if call_count[0] == 2:
            return ChatResponse(
                content=None,
                tool_calls=[{"id": "t2", "name": "synthesize_remediation", "input": synthesis_input}],
                stop_reason="tool_use", tokens_used=40, model="test",
            )
        return ChatResponse(
            content=json.dumps({"status": "synthesis_complete"}),
            tool_calls=[], stop_reason="end_turn", tokens_used=10, model="test",
        )

    mock = MagicMock()
    mock.chat.side_effect = lambda **kw: _chat(**kw)
    return mock


# ── A. inv_context shape from BlockedPipelineError ────────────────────────────

class TestInvContextBuilding(unittest.TestCase):
    """
    Verify the inv_context dict built in _run_taclaw_job matches
    what TAclawInvestigationAgent expects.
    """

    def _build_inv_context(self, exc, arch_name="test_arch", job_id="j_test",
                           merged=None):
        """Replicate the inv_context building logic from _run_taclaw_job."""
        if merged is None:
            merged = _make_merged_graph()

        _bouncer_reason = getattr(exc, "reason", "unknown")
        _blocked_ctx    = getattr(exc, "ctx", None)
        _detect_summary = getattr(_blocked_ctx, "detect_summary", {}) if _blocked_ctx else {}
        _fired_rules    = _detect_summary.get("rules_fired", [])
        _max_sev = next(
            (r.get("severity", "") for r in _fired_rules if isinstance(r, dict)),
            "",
        ) if _fired_rules and isinstance(_fired_rules[0], dict) else ""
        _fired_ids = [
            r["rule_id"] if isinstance(r, dict) else str(r)
            for r in _fired_rules
        ]
        return {
            "job_id":             job_id,
            "arch_name":          arch_name,
            "arch_type":          merged.adapter_metadata.get("primary_arch_type", ""),
            "gate":               "BLOCK",
            "bouncer_reason":     _bouncer_reason,
            "fired_detect_rules": _fired_ids,
            "max_severity":       _max_sev,
            "pipeline_result":    {},
        }

    def test_reason_extracted(self):
        exc = _make_blocked_exc("exploitation.blocked=True")
        ctx = self._build_inv_context(exc)
        self.assertEqual(ctx["bouncer_reason"], "exploitation.blocked=True")
        self.assertEqual(ctx["gate"], "BLOCK")

    def test_rule_ids_extracted(self):
        exc = _make_blocked_exc(detect_rules=[
            {"rule_id": "DETECT-INJ-001", "severity": "Critical"},
            {"rule_id": "DETECT-QC-009", "severity": "High"},
        ])
        ctx = self._build_inv_context(exc)
        self.assertIn("DETECT-INJ-001", ctx["fired_detect_rules"])
        self.assertIn("DETECT-QC-009", ctx["fired_detect_rules"])

    def test_max_severity_extracted(self):
        exc = _make_blocked_exc(detect_rules=[{"rule_id": "DETECT-INJ-001", "severity": "Critical"}])
        ctx = self._build_inv_context(exc)
        self.assertEqual(ctx["max_severity"], "Critical")

    def test_arch_type_from_merged(self):
        exc = _make_blocked_exc()
        merged = _make_merged_graph(arch_type="agentic_ai")
        ctx = self._build_inv_context(exc, merged=merged)
        self.assertEqual(ctx["arch_type"], "agentic_ai")

    def test_empty_detect_rules(self):
        exc = _make_blocked_exc("kill_switch", detect_rules=[])
        ctx = self._build_inv_context(exc)
        self.assertEqual(ctx["fired_detect_rules"], [])
        self.assertEqual(ctx["max_severity"], "")

    def test_agent_accepts_context(self):
        """The built context must pass should_run (non-trivial bouncer reason)."""
        from chatbot.agents.managed.taclaw_investigator import TAclawInvestigationAgent
        exc = _make_blocked_exc("exploitation.blocked=True")
        ctx = self._build_inv_context(exc)
        agent = TAclawInvestigationAgent()
        ok, reason = agent.should_run(ctx)
        self.assertTrue(ok, f"should_run rejected context: {reason}")

    def test_trivial_block_context_skipped(self):
        """kill_switch context should be skipped by the agent."""
        from chatbot.agents.managed.taclaw_investigator import TAclawInvestigationAgent
        exc = _make_blocked_exc("kill_switch")
        ctx = self._build_inv_context(exc)
        agent = TAclawInvestigationAgent()
        ok, _ = agent.should_run(ctx)
        self.assertFalse(ok)


# ── B. Full _run_taclaw_job wire-in (async end-to-end) ───────────────────────

import importlib as _importlib
_FASTAPI_AVAILABLE = _importlib.util.find_spec("fastapi") is not None


def _make_artifacts(n=2):
    from chatbot.adapters import CrawledArtifact
    arts = []
    for i in range(n):
        a = MagicMock(spec=CrawledArtifact)
        a.path = Path(f"/tmp/fake_{i}.mmd")
        a.adapter_type = "mmd"
        arts.append(a)
    return arts


@unittest.skipUnless(_FASTAPI_AVAILABLE, "fastapi not installed — skipping wire-in tests")
class TestTAclawWireIn(unittest.IsolatedAsyncioTestCase):
    """
    Run _run_taclaw_job end-to-end with mocked heavy dependencies.
    Verifies that result['investigation'] is populated on BLOCK.
    """

    async def _run_job(self, blocked_exc, investigation_mock_client=None):
        """Helper: set up all mocks and run _run_taclaw_job, return final job result."""
        from chatbot.api.routes.taclaw import _run_taclaw_job
        from chatbot.api.job_store import Job
        from chatbot.modules.agent_passport import AgentPassport

        job = MagicMock(spec=Job)
        job.job_id = "test_job_001"

        passport = MagicMock(spec=AgentPassport)
        passport.passport_id.return_value = "pp_test"
        passport.to_provenance.return_value = {"passport_id": "pp_test"}

        store = MagicMock()
        captured: dict = {}

        def _store_update(job_id, **kwargs):
            captured.update(kwargs)

        store.update.side_effect = _store_update

        artifacts = _make_artifacts(2)
        merged = _make_merged_graph("microservices")

        fake_graph_list = [MagicMock()]

        with (
            patch("chatbot.api.routes.taclaw.get_job_store", return_value=store),
            patch("chatbot.api.routes.taclaw._validate_passport",
                  return_value=(True, "ok", {})),
            patch("chatbot.api.routes.taclaw.RepoCrawler") as MockCrawler,
            patch("chatbot.api.routes.taclaw.get_settings") as mock_settings,
            patch("chatbot.api.routes.taclaw.select_mode") as mock_route,
            patch("chatbot.api.routes.taclaw._preflight_authority_gate",
                  return_value=MagicMock(preflight={"blocked": False})),
            patch("chatbot.api.routes.taclaw.ThreatAssessorHarness") as MockHarness,
            patch("chatbot.api.routes.taclaw.build_export", return_value={"gate": {"result": "BLOCK"}}),
            patch("chatbot.api.routes.taclaw.build_brain"),
            patch("chatbot.api.routes.taclaw.query_brain", return_value={}),
            patch("agentic.llm_client.LLMClient",
                  return_value=(investigation_mock_client or _make_synthesis_chat_responses())),
            patch("chatbot.agents.managed.taclaw_investigator._load_brain",
                  return_value={"patterns": []}),
            patch("chatbot.agents.managed.taclaw_investigator._load_rules", return_value={}),
        ):
            # Settings
            settings = MagicMock()
            settings.system.report_dir = "/tmp/ta_test_reports"
            mock_settings.return_value = settings

            # Crawler returns fake artifacts
            crawler_instance = MagicMock()
            crawler_instance.crawl.return_value = artifacts
            MockCrawler.return_value = crawler_instance

            # Smart router → api_only
            routing = MagicMock()
            routing.mode = "api_only"
            routing.model_id = None
            routing.model_alias = None
            mock_route.return_value = routing

            # Adapter merging: patch the adapter imports used inside _run_taclaw_job
            with patch("chatbot.api.routes.taclaw.MermaidAdapter") as MockMmd:
                mock_graph = MagicMock()
                mock_graph.nodes = [MagicMock()]
                mock_graph.edges = []
                mock_graph.adapter_metadata = merged.adapter_metadata
                mock_graph.source_trust = "unverified"
                MockMmd.return_value.parse.return_value = mock_graph

                # Harness raises BlockedPipelineError
                harness_instance = MagicMock()
                harness_instance.run_typed.side_effect = blocked_exc
                MockHarness.return_value = harness_instance

                # ArchitectureGraph.merge — return our merged mock
                with patch("chatbot.api.routes.taclaw.ArchitectureGraph") as MockAG:
                    MockAG.merge.return_value = merged

                    await _run_taclaw_job(
                        job=job,
                        target_type="directory",
                        target="/tmp/fake_arch",
                        arch_name="injection_test",
                        ssp_profile="low_risk_cloud",
                        enrich_from_github=False,
                        github_repo=None,
                        passport=passport,
                        passport_token="tok_test",
                    )

        return captured

    async def test_investigation_present_on_block(self):
        exc = _make_blocked_exc("exploitation.blocked=True")
        result = await self._run_job(exc)
        self.assertIn("investigation", result.get("result", {}),
                      "result['investigation'] not present after BLOCK")

    async def test_investigation_has_remediation_steps(self):
        exc = _make_blocked_exc("exploitation.blocked=True")
        result = await self._run_job(exc)
        inv = result.get("result", {}).get("investigation", {})
        self.assertIn("remediation_steps", inv,
                      f"remediation_steps missing from investigation: {inv}")
        self.assertGreater(len(inv["remediation_steps"]), 0)

    async def test_investigation_has_agent_meta(self):
        exc = _make_blocked_exc("exploitation.blocked=True")
        result = await self._run_job(exc)
        inv = result.get("result", {}).get("investigation", {})
        meta = inv.get("_agent_meta", {})
        self.assertIn("tool_calls_made", meta)
        self.assertIn("tokens_used", meta)

    async def test_kill_switch_investigation_skipped(self):
        """kill_switch block → investigation skipped (not an error)."""
        exc = _make_blocked_exc("kill_switch")
        result = await self._run_job(exc)
        inv = result.get("result", {}).get("investigation", {})
        self.assertTrue(
            inv.get("skipped") is True or inv == {},
            f"Expected skipped investigation for kill_switch, got: {inv}",
        )

    async def test_pass_gate_no_investigation(self):
        """gate=PASS should produce no investigation at all."""
        from chatbot.api.routes.taclaw import _run_taclaw_job
        from chatbot.api.job_store import Job

        job = MagicMock(spec=Job)
        job.job_id = "pass_job"

        store = MagicMock()
        captured: dict = {}
        store.update.side_effect = lambda job_id, **kw: captured.update(kw)

        artifacts = _make_artifacts(1)
        merged = _make_merged_graph()

        with (
            patch("chatbot.api.routes.taclaw.get_job_store", return_value=store),
            patch("chatbot.api.routes.taclaw._validate_passport",
                  return_value=(True, "ok", {})),
            patch("chatbot.api.routes.taclaw.RepoCrawler") as MockCrawler,
            patch("chatbot.api.routes.taclaw.get_settings") as mock_settings,
            patch("chatbot.api.routes.taclaw.select_mode") as mock_route,
            patch("chatbot.api.routes.taclaw._preflight_authority_gate",
                  return_value=MagicMock(preflight={"blocked": False})),
            patch("chatbot.api.routes.taclaw.ThreatAssessorHarness") as MockHarness,
            patch("chatbot.api.routes.taclaw.build_export", return_value={"gate": {"result": "PASS"}}),
            patch("chatbot.api.routes.taclaw.build_brain"),
            patch("chatbot.api.routes.taclaw.query_brain", return_value={}),
        ):
            settings = MagicMock()
            settings.system.report_dir = "/tmp/ta_test_reports"
            mock_settings.return_value = settings

            crawler_instance = MagicMock()
            crawler_instance.crawl.return_value = artifacts
            MockCrawler.return_value = crawler_instance

            routing = MagicMock()
            routing.mode = "api_only"
            routing.model_id = None
            routing.model_alias = None
            mock_route.return_value = routing

            harness_instance = MagicMock()
            harness_instance.run_typed.return_value = MagicMock()
            MockHarness.return_value = harness_instance

            with patch("chatbot.api.routes.taclaw.MermaidAdapter") as MockMmd:
                mock_graph = MagicMock()
                mock_graph.nodes = [MagicMock()]
                mock_graph.edges = []
                mock_graph.adapter_metadata = merged.adapter_metadata
                mock_graph.source_trust = "unverified"
                MockMmd.return_value.parse.return_value = mock_graph

                with patch("chatbot.api.routes.taclaw.ArchitectureGraph") as MockAG:
                    MockAG.merge.return_value = merged

                    await _run_taclaw_job(
                        job=job,
                        target_type="directory",
                        target="/tmp/fake_arch",
                        arch_name="pass_test",
                        ssp_profile="low_risk_cloud",
                        enrich_from_github=False,
                        github_repo=None,
                        passport=None,
                        passport_token=None,
                    )

        inv = captured.get("result", {}).get("investigation", {})
        self.assertEqual(inv, {}, f"Expected empty investigation on PASS, got: {inv}")


# ── C. Investigation context schema (standalone) ──────────────────────────────

class TestInvContextSchema(unittest.TestCase):
    """
    The investigation dict written into result must always have
    a consistent shape so callers can rely on it.
    """

    REQUIRED_KEYS_SUCCESS = {"block_summary", "root_signals", "brain_context",
                             "remediation_steps", "confidence", "agent_id"}
    REQUIRED_KEYS_SKIP    = {"skipped", "reason"}

    def test_success_output_schema(self):
        from chatbot.agents.managed.taclaw_investigator import TAclawInvestigationAgent
        from agentic.llm_client import ChatResponse

        synthesis = {
            "block_summary": "Test block",
            "root_signals": ["DETECT-INJ-001"],
            "brain_context": "none",
            "remediation_steps": ["Fix it"],
            "confidence": "medium",
        }
        call_count = [0]

        def _chat(**kw):
            call_count[0] += 1
            if call_count[0] == 1:
                return ChatResponse(
                    content=None,
                    tool_calls=[{"id": "t1", "name": "synthesize_remediation", "input": synthesis}],
                    stop_reason="tool_use", tokens_used=20, model="m",
                )
            return ChatResponse(content="{}", tool_calls=[], stop_reason="end_turn",
                                tokens_used=5, model="m")

        mock_client = MagicMock()
        mock_client.chat.side_effect = lambda **kw: _chat(**kw)

        agent = TAclawInvestigationAgent()
        ctx = {
            "job_id": "j", "arch_name": "a", "arch_type": "generic",
            "gate": "BLOCK", "bouncer_reason": "exploitation.blocked=True",
            "fired_detect_rules": ["DETECT-INJ-001"], "max_severity": "Critical",
            "pipeline_result": {},
        }
        with (
            patch("agentic.llm_client.LLMClient", return_value=mock_client),
            patch("chatbot.agents.managed.taclaw_investigator._load_brain", return_value={"patterns": []}),
            patch("chatbot.agents.managed.taclaw_investigator._load_rules", return_value={}),
        ):
            result = agent.run(ctx)

        self.assertTrue(result.success)
        for k in self.REQUIRED_KEYS_SUCCESS:
            self.assertIn(k, result.output, f"Missing key '{k}' in investigation output")

    def test_skip_output_schema(self):
        from chatbot.agents.managed.taclaw_investigator import TAclawInvestigationAgent
        agent = TAclawInvestigationAgent()
        result = agent.run({"gate": "BLOCK", "bouncer_reason": "kill_switch"})
        self.assertFalse(result.success)
        self.assertIn("kill_switch", result.skip_reason)


if __name__ == "__main__":
    unittest.main()
