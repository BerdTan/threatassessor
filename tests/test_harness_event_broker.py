"""
Tests for the EventBroker pipeline telemetry layer.

Covers:
  - HarnessEvent construction and serialisation
  - EventBrokerCritic: policy loading, settings override, sink registration
  - EventBrokerCritic.emit(): fan-out, per-sink isolation, disabled guard
  - BaseSink._should_handle() and _matches_preset() subscription filtering
  - SiemSink: file-write path, SiemEvent schema translation, webhook fallback
  - LangfuseSink: credential resolution, Langfuse call mapping per event type
  - WebhookSink: POST serialisation
  - Integration: multi-sink fan-out smoke

No LLM calls, no network (all external calls are mocked), no API key required.
Expected runtime: ~1 second.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, call, patch

import pytest

from chatbot.harness.event_broker import EventBrokerCritic, HarnessEvent, EVENT_TYPES
from chatbot.harness.sinks import BaseSink, SiemSink, LangfuseSink, WebhookSink


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _event(event_type: str = "run_start", source: str = "test",
           run_id: str = "test_run_001", payload: Dict[str, Any] | None = None) -> HarnessEvent:
    return HarnessEvent(
        event_type=event_type,
        source=source,
        run_id=run_id,
        ts="2026-07-13T10:00:00Z",
        payload=payload or {},
    )


def _siem_cfg(**kwargs) -> dict:
    base = {"enabled": True, "sink_path": "", "events": []}
    base.update(kwargs)
    return base


def _langfuse_cfg(**kwargs) -> dict:
    base = {
        "enabled": True,
        "host": "http://localhost:3000",
        "public_key": "pk-test",
        "secret_key": "sk-test",
        "events": [],
    }
    base.update(kwargs)
    return base


def _webhook_cfg(**kwargs) -> dict:
    base = {"enabled": True, "url": "http://example.com/hook", "events": []}
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# HarnessEvent
# ---------------------------------------------------------------------------

class TestHarnessEvent:
    def test_to_dict_round_trips(self):
        ev = _event("stage_complete", "analysis", payload={"confidence": 0.85})
        d = ev.to_dict()
        assert d["event_type"] == "stage_complete"
        assert d["source"] == "analysis"
        assert d["run_id"] == "test_run_001"
        assert d["payload"]["confidence"] == 0.85

    def test_all_event_types_are_valid(self):
        for et in EVENT_TYPES:
            ev = _event(et)
            assert ev.event_type == et

    def test_default_payload_is_empty_dict(self):
        ev = HarnessEvent(event_type="run_start", source="harness",
                          run_id="x", ts="2026-01-01T00:00:00Z")
        assert ev.payload == {}


# ---------------------------------------------------------------------------
# EventBrokerCritic — policy loading and settings override
# ---------------------------------------------------------------------------

class TestEventBrokerInit:
    def test_disabled_when_policy_missing(self, tmp_path):
        broker = EventBrokerCritic(policy_path=str(tmp_path / "nonexistent.yaml"))
        assert broker._enabled is False
        assert broker._sinks == []

    def test_disabled_when_no_event_broker_section(self, tmp_path):
        p = tmp_path / "policy.yaml"
        p.write_text("agent_policy:\n  blocked_agents_on_critical: []\n")
        broker = EventBrokerCritic(policy_path=str(p))
        assert broker._enabled is False

    def test_disabled_when_no_sinks_enabled(self, tmp_path):
        p = tmp_path / "policy.yaml"
        p.write_text(
            "event_broker:\n"
            "  sinks:\n"
            "    siem:\n"
            "      enabled: false\n"
            "    langfuse:\n"
            "      enabled: false\n"
            "    webhook:\n"
            "      enabled: false\n"
        )
        broker = EventBrokerCritic(policy_path=str(p))
        assert broker._enabled is False
        assert broker._sinks == []

    def test_siem_sink_registered_when_enabled(self, tmp_path):
        sink_path = str(tmp_path / "siem.jsonl")
        p = tmp_path / "policy.yaml"
        yaml_content = (
            "event_broker:\n"
            "  sinks:\n"
            "    siem:\n"
            "      enabled: true\n"
            "      sink_path: " + sink_path + "\n"
        )
        p.write_text(yaml_content)
        # settings.event_broker.enabled defaults to False; override to True
        with patch("chatbot.config.settings.get_settings") as mock_settings:
            mock_eb = MagicMock()
            mock_eb.enabled = True
            mock_settings.return_value.event_broker = mock_eb
            broker = EventBrokerCritic(policy_path=str(p))
        assert broker._enabled is True
        assert any(isinstance(s, SiemSink) for s in broker._sinks)

    def test_settings_override_disables_broker(self, tmp_path):
        p = tmp_path / "policy.yaml"
        p.write_text(
            "event_broker:\n"
            "  sinks:\n"
            "    siem:\n"
            "      enabled: true\n"
        )
        # get_settings is imported locally inside _load_sinks
        with patch("chatbot.config.settings.get_settings") as mock_settings:
            mock_eb = MagicMock()
            mock_eb.enabled = False
            mock_settings.return_value.event_broker = mock_eb
            broker = EventBrokerCritic(policy_path=str(p))
        assert broker._enabled is False

    def test_critique_stub_returns_none(self, tmp_path):
        broker = EventBrokerCritic(policy_path=str(tmp_path / "none.yaml"))
        assert broker.critique() is None


# ---------------------------------------------------------------------------
# EventBrokerCritic.emit() — fan-out and isolation
# ---------------------------------------------------------------------------

class TestEventBrokerEmit:
    def _broker_with_mock_sinks(self, n: int = 2) -> tuple:
        """Return (broker, [sink1, sink2, ...]) with pre-wired mock sinks."""
        broker = EventBrokerCritic.__new__(EventBrokerCritic)
        broker._enabled = True
        sinks = [MagicMock() for _ in range(n)]
        broker._sinks = sinks
        broker._current_trace = None
        return broker, sinks

    def test_emit_calls_all_sinks(self):
        broker, sinks = self._broker_with_mock_sinks(3)
        ev = _event("run_start")
        broker.emit(ev)
        for sink in sinks:
            sink.emit.assert_called_once_with(ev)

    def test_emit_noop_when_disabled(self):
        broker, sinks = self._broker_with_mock_sinks()
        broker._enabled = False
        broker.emit(_event("run_start"))
        for sink in sinks:
            sink.emit.assert_not_called()

    def test_emit_noop_when_no_sinks(self):
        broker, _ = self._broker_with_mock_sinks()
        broker._sinks = []
        broker._enabled = True
        # Should not raise even with no sinks
        broker.emit(_event("run_start"))

    def test_failing_sink_does_not_stop_others(self):
        broker, sinks = self._broker_with_mock_sinks(3)
        sinks[1].emit.side_effect = RuntimeError("sink 2 exploded")
        broker.emit(_event("run_start"))
        # sink 0 and sink 2 must still be called
        sinks[0].emit.assert_called_once()
        sinks[2].emit.assert_called_once()

    def test_flush_calls_all_sinks(self):
        broker, sinks = self._broker_with_mock_sinks(2)
        broker.flush()
        for sink in sinks:
            sink.flush.assert_called_once()

    def test_flush_tolerates_sink_exception(self):
        broker, sinks = self._broker_with_mock_sinks(2)
        sinks[0].flush.side_effect = Exception("flush exploded")
        broker.flush()  # must not raise
        sinks[1].flush.assert_called_once()


# ---------------------------------------------------------------------------
# BaseSink — subscription filtering
# ---------------------------------------------------------------------------

class TestBaseSinkFiltering:
    # BaseSink is abstract — use SiemSink (concrete) for filtering tests

    def _sink(self, events):
        # Use a null sink path so no file I/O occurs in filtering tests
        return SiemSink({"events": events, "sink_path": "/dev/null"})

    def test_empty_subscription_handles_all_events(self):
        sink = self._sink([])
        for et in EVENT_TYPES:
            assert sink._should_handle(_event(et)) is True

    def test_explicit_event_type_subscription(self):
        sink = self._sink(["run_complete"])
        assert sink._should_handle(_event("run_complete")) is True
        assert sink._should_handle(_event("run_start")) is False

    def test_stage_trace_preset_expands_correctly(self):
        # "stage_trace" preset → run_start, stage_complete, run_complete
        sink = self._sink(["stage_trace"])
        assert sink._should_handle(_event("run_start")) is True
        assert sink._should_handle(_event("stage_complete")) is True
        assert sink._should_handle(_event("run_complete")) is True
        assert sink._should_handle(_event("critic_complete")) is False

    def test_critic_trace_preset(self):
        sink = self._sink(["critic_trace"])
        assert sink._should_handle(_event("critic_complete")) is True
        assert sink._should_handle(_event("stage_complete")) is False

    def test_governance_preset(self):
        sink = self._sink(["governance"])
        assert sink._should_handle(_event("governance_complete")) is True
        assert sink._should_handle(_event("aivss_complete")) is False

    def test_aivss_preset(self):
        sink = self._sink(["aivss"])
        assert sink._should_handle(_event("aivss_complete")) is True
        assert sink._should_handle(_event("aivss_gate")) is True
        assert sink._should_handle(_event("governance_complete")) is False

    def test_multiple_presets_combined(self):
        sink = self._sink(["governance", "aivss"])
        assert sink._should_handle(_event("governance_complete")) is True
        assert sink._should_handle(_event("aivss_complete")) is True
        assert sink._should_handle(_event("critic_complete")) is False


# ---------------------------------------------------------------------------
# SiemSink — file write path and schema translation
# ---------------------------------------------------------------------------

class TestSiemSink:
    def test_emit_writes_jsonl_line(self, tmp_path):
        sink_path = tmp_path / "siem.jsonl"
        sink = SiemSink(_siem_cfg(sink_path=str(sink_path)))
        sink.emit(_event("run_start", payload={"scenario": "api_only"}))
        lines = sink_path.read_text().strip().splitlines()
        assert len(lines) == 1
        record = json.loads(lines[0])
        assert record["event_type"] == "run_start"

    def test_multiple_emits_append(self, tmp_path):
        sink_path = tmp_path / "siem.jsonl"
        sink = SiemSink(_siem_cfg(sink_path=str(sink_path)))
        for et in ["run_start", "stage_complete", "run_complete"]:
            sink.emit(_event(et))
        lines = sink_path.read_text().strip().splitlines()
        assert len(lines) == 3

    def test_aivss_gate_translated_to_siem_schema(self, tmp_path):
        sink_path = tmp_path / "siem.jsonl"
        sink = SiemSink(_siem_cfg(sink_path=str(sink_path)))
        payload = {
            "outbound_score": 8.5,
            "overall_severity": "HIGH",
            "top_threat": {"technique_id": "AP-1", "composite": 8.5},
            "aivss_inbound":  1.2,
            "aivss_internal": 5.0,
            "aivss_outbound": 8.5,
        }
        sink.emit(_event("aivss_gate", payload=payload))
        record = json.loads(sink_path.read_text().strip())
        assert record["event_type"] == "threat_assessment_complete"
        assert record["overall_severity"] == "HIGH"

    def test_governance_complete_translated(self, tmp_path):
        sink_path = tmp_path / "siem.jsonl"
        sink = SiemSink(_siem_cfg(sink_path=str(sink_path)))
        payload = {
            "overall_risk_level": "HIGH",
            "architecture": "test_arch",
            "D1": "MEDIUM",
            "D2": "LOW",
            "D3": "HIGH",
            "D4": "LOW",
            "D5": "LOW",
            "blocked_agents": ["blackhat"],
        }
        sink.emit(_event("governance_complete", payload=payload))
        record = json.loads(sink_path.read_text().strip())
        assert record["event_type"] == "governance_complete"
        assert record["blocked_agents"] == ["blackhat"]

    def test_subscription_filter_respected(self, tmp_path):
        sink_path = tmp_path / "siem.jsonl"
        # Only subscribe to governance events
        sink = SiemSink(_siem_cfg(sink_path=str(sink_path), events=["governance"]))
        sink.emit(_event("run_start"))           # not subscribed
        sink.emit(_event("governance_complete")) # subscribed
        lines = sink_path.read_text().strip().splitlines() if sink_path.exists() else []
        assert len(lines) == 1

    def test_webhook_called_when_url_set(self, tmp_path):
        sink_path = tmp_path / "siem.jsonl"
        sink = SiemSink(_siem_cfg(sink_path=str(sink_path), webhook_url="http://hook.test/event"))
        # urllib.request is imported locally in _post_webhook — patch at stdlib level
        with patch("urllib.request.urlopen") as mock_urlopen:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = lambda s: s
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_urlopen.return_value = mock_ctx
            sink.emit(_event("run_start"))
        mock_urlopen.assert_called_once()

    def test_file_write_failure_does_not_raise(self, tmp_path):
        sink = SiemSink(_siem_cfg(sink_path="/nonexistent_dir_xyz/siem.jsonl"))
        sink.emit(_event("run_start"))  # must not raise


# ---------------------------------------------------------------------------
# LangfuseSink — credential resolution and event→call mapping
# ---------------------------------------------------------------------------

class TestLangfuseSink:
    """
    All Langfuse SDK calls are mocked via patch("chatbot.harness.sinks.Langfuse").
    Tests verify the correct SDK method is called with the right arguments for each
    event type. No real Langfuse server required.
    """

    def _sink_with_mock_lf(self) -> tuple:
        """Return (sink, mock_langfuse_instance) with _lf pre-wired.
        Langfuse is a local import inside _init_client — patch at langfuse.Langfuse."""
        with patch("langfuse.Langfuse") as MockLf:
            mock_lf = MagicMock()
            MockLf.return_value = mock_lf
            sink = LangfuseSink(_langfuse_cfg())
        # After the context exits the patch is gone, but sink._lf holds the mock instance
        return sink, mock_lf

    def test_init_creates_langfuse_client(self):
        with patch("langfuse.Langfuse") as MockLf:
            sink = LangfuseSink(_langfuse_cfg(public_key="pk-x", secret_key="sk-x"))
        MockLf.assert_called_once_with(
            public_key="pk-x",
            secret_key="sk-x",
            host="http://localhost:3000",
        )
        assert sink._lf is not None

    def test_missing_keys_leaves_lf_none(self):
        # Empty public_key and secret_key — _lf must stay None
        # Ensure env vars are absent so fallback also fails
        env_clean = {k: v for k, v in os.environ.items()
                     if k not in ("LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY", "LANGFUSE_BASE_URL")}
        with patch.dict(os.environ, env_clean, clear=True):
            sink = LangfuseSink(_langfuse_cfg(public_key="", secret_key=""))
        assert sink._lf is None

    def test_env_var_fallback_for_credentials(self):
        # The code reads LANGFUSE_BASE_URL for host (verified in sinks.py line 189)
        # but defaults to localhost:3000 if not set — test the key/secret resolution
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-env",
            "LANGFUSE_SECRET_KEY": "sk-env",
        }):
            with patch("langfuse.Langfuse") as MockLf:
                sink = LangfuseSink(_langfuse_cfg(public_key="", secret_key=""))
        MockLf.assert_called_once_with(
            public_key="pk-env",
            secret_key="sk-env",
            host="http://localhost:3000",  # default since LANGFUSE_BASE_URL not set
        )

    def test_config_keys_take_priority_over_env(self):
        with patch.dict(os.environ, {
            "LANGFUSE_PUBLIC_KEY": "pk-env",
            "LANGFUSE_SECRET_KEY": "sk-env",
        }):
            with patch("langfuse.Langfuse") as MockLf:
                sink = LangfuseSink(_langfuse_cfg(public_key="pk-config", secret_key="sk-config"))
        MockLf.assert_called_once_with(
            public_key="pk-config",
            secret_key="sk-config",
            host="http://localhost:3000",
        )

    def test_emit_noop_when_lf_none(self):
        sink = LangfuseSink.__new__(LangfuseSink)
        sink._lf = None
        sink._config = {"events": []}
        sink._subscribed = []
        sink._current_trace = None
        sink._trace = None
        # Must not raise even though _lf is None
        sink.emit(_event("run_start"))

    def test_run_start_creates_trace(self):
        sink, mock_lf = self._sink_with_mock_lf()
        mock_trace = MagicMock()
        mock_lf.trace.return_value = mock_trace
        sink.emit(_event("run_start", run_id="arch_20260713", payload={"scenario": "full_moe"}))
        mock_lf.trace.assert_called_once()
        call_kwargs = mock_lf.trace.call_args
        # id should contain the run_id
        assert "arch_20260713" in str(call_kwargs)

    def test_stage_complete_creates_span(self):
        sink, mock_lf = self._sink_with_mock_lf()
        mock_trace = MagicMock()
        mock_lf.trace.return_value = mock_trace
        sink._trace = mock_trace
        sink.emit(_event("stage_complete", source="analysis"))
        mock_trace.span.assert_called_once()
        call_kwargs = mock_trace.span.call_args
        assert "analysis" in str(call_kwargs)

    def test_critic_complete_creates_generation(self):
        sink, mock_lf = self._sink_with_mock_lf()
        mock_trace = MagicMock()
        sink._trace = mock_trace
        payload = {
            "model": "claude-sonnet-4-5",
            "total_tokens": 1200,
            "total_cost": 0.015,
        }
        sink.emit(_event("critic_complete", source="red_team", payload=payload))
        mock_trace.generation.assert_called_once()
        call_str = str(mock_trace.generation.call_args)
        assert "red_team" in call_str

    def test_governance_complete_updates_trace(self):
        sink, mock_lf = self._sink_with_mock_lf()
        mock_trace = MagicMock()
        sink._trace = mock_trace
        payload = {"overall_risk_level": "HIGH", "D1": "HIGH", "D2": "LOW",
                   "D3": "HIGH", "D4": "LOW", "D5": "LOW", "blocked_agents": []}
        sink.emit(_event("governance_complete", payload=payload))
        mock_trace.update.assert_called_once()

    def test_aivss_complete_creates_span(self):
        sink, mock_lf = self._sink_with_mock_lf()
        mock_trace = MagicMock()
        sink._trace = mock_trace
        payload = {"inbound": {"composite": 0.0}, "internal": {"composite": 6.25},
                   "outbound": {"composite": 0.0}, "overall_severity": "MEDIUM"}
        sink.emit(_event("aivss_complete", payload=payload))
        mock_trace.span.assert_called_once()

    def test_run_complete_updates_trace_output(self):
        sink, mock_lf = self._sink_with_mock_lf()
        mock_trace = MagicMock()
        sink._trace = mock_trace
        payload = {"confidence": 73.3, "errors": []}
        sink.emit(_event("run_complete", payload=payload))
        mock_trace.update.assert_called_once()

    def test_flush_calls_langfuse_flush(self):
        sink, mock_lf = self._sink_with_mock_lf()
        sink.flush()
        mock_lf.flush.assert_called_once()

    def test_flush_noop_when_lf_none(self):
        sink = LangfuseSink.__new__(LangfuseSink)
        sink._lf = None
        sink._config = {}
        sink._subscribed = []
        sink.flush()  # must not raise

    def test_langfuse_not_installed_leaves_lf_none(self):
        # Simulate langfuse not installed by raising ImportError when langfuse.Langfuse is accessed
        with patch("langfuse.Langfuse", side_effect=ImportError("no module named langfuse")):
            sink = LangfuseSink(_langfuse_cfg())
        assert sink._lf is None


# ---------------------------------------------------------------------------
# WebhookSink — POST serialisation
# ---------------------------------------------------------------------------

class TestWebhookSink:
    def test_emit_posts_event_as_json(self):
        sink = WebhookSink(_webhook_cfg(url="http://hook.test/ev"))
        with patch("urllib.request.urlopen") as mock_open:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = lambda s: s
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_ctx
            sink.emit(_event("run_complete", payload={"confidence": 80.0}))
        mock_open.assert_called_once()
        req = mock_open.call_args[0][0]
        body = json.loads(req.data)
        assert body["event_type"] == "run_complete"
        assert body["payload"]["confidence"] == 80.0

    def test_emit_noop_when_no_url(self):
        sink = WebhookSink({"url": "", "events": []})
        with patch("urllib.request.urlopen") as mock_open:
            sink.emit(_event("run_complete"))
        mock_open.assert_not_called()

    def test_webhook_failure_does_not_raise(self):
        sink = WebhookSink(_webhook_cfg(url="http://hook.test/ev"))
        with patch("urllib.request.urlopen", side_effect=OSError("connection refused")):
            sink.emit(_event("run_start"))  # must not raise

    def test_subscription_filter_respected(self):
        sink = WebhookSink(_webhook_cfg(url="http://hook.test/ev", events=["governance"]))
        with patch("urllib.request.urlopen") as mock_open:
            mock_ctx = MagicMock()
            mock_ctx.__enter__ = lambda s: s
            mock_ctx.__exit__ = MagicMock(return_value=False)
            mock_open.return_value = mock_ctx
            sink.emit(_event("run_start"))           # not subscribed — no POST
            sink.emit(_event("governance_complete")) # subscribed — POST
        assert mock_open.call_count == 1


# ---------------------------------------------------------------------------
# Integration smoke — multi-sink fan-out
# ---------------------------------------------------------------------------

class TestMultiSinkIntegration:
    def test_broker_fans_out_to_all_three_sinks(self, tmp_path):
        """EventBroker with SiemSink + mocked LangfuseSink + mocked WebhookSink."""
        siem_path = tmp_path / "siem.jsonl"

        # Wire broker directly without YAML policy
        broker = EventBrokerCritic.__new__(EventBrokerCritic)
        broker._current_trace = None
        broker._enabled = True

        siem_sink = SiemSink(_siem_cfg(sink_path=str(siem_path)))
        lf_sink   = MagicMock(spec=LangfuseSink)
        wh_sink   = MagicMock(spec=WebhookSink)

        broker._sinks = [siem_sink, lf_sink, wh_sink]

        events = [
            _event("run_start", payload={"scenario": "full_moe"}),
            _event("stage_complete", source="analysis"),
            _event("governance_complete", payload={"overall_risk_level": "LOW"}),
            _event("run_complete", payload={"confidence": 75.0, "errors": []}),
        ]
        for ev in events:
            broker.emit(ev)
        broker.flush()

        # SiemSink wrote 4 lines
        lines = siem_path.read_text().strip().splitlines()
        assert len(lines) == 4

        # Langfuse mock received 4 emit calls + 1 flush
        assert lf_sink.emit.call_count == 4
        lf_sink.flush.assert_called_once()

        # Webhook mock received 4 emit calls
        assert wh_sink.emit.call_count == 4
